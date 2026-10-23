"""Validate encoded media and scene coverage. Does not perform ASR or visual acceptance."""
import argparse
import json
import math
from pathlib import Path
import re
import sys


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def check_timeline(data, report):
    errors = report['errors']
    duration = data.get('duration')
    scenes = data.get('scenes')
    if not positive(duration) or not isinstance(scenes, list) or not scenes:
        raise ValueError('Timeline needs positive duration and a nonempty scenes array.')
    previous = 0.0
    captions = []
    for i, scene in enumerate(scenes):
        start, end = scene.get('start'), scene.get('end')
        if not isinstance(start, (int, float)) or not math.isfinite(start) or not positive(end) or not 0 <= start < end <= duration + .001:
            raise ValueError(f'Invalid time range in scene {i+1}.')
        if abs(start - previous) > .05:
            errors.append(f'Scene {i+1}: gap or overlap in semantic timeline (use separate transition intervals).')
        if not isinstance(scene.get('caption'), str) or not scene['caption'].strip():
            errors.append(f'Scene {i+1}: missing caption.')
        captions.append(scene.get('caption', ''))
        previous = end
    if abs(previous-duration) > .05:
        errors.append('Scenes do not cover timeline ending.')
    source = data.get('narration_text')
    if isinstance(source, str) and source.strip():
        # Whitespace only: punctuation, numbers and words must remain unchanged.
        normalize = lambda value: re.sub(r'\s+', '', value)
        report['caption_text_checked'] = True
        if normalize(source) != normalize(''.join(captions)):
            errors.append('Caption text differs from narration_text (whitespace ignored only).')
    else:
        report['caption_text_checked'] = False
        report['warnings'].append('No narration_text: content completeness was NOT checked.')
    if not data.get('alignment'):
        errors.append('Missing alignment method; do not imply word-level synchronization.')
    if data.get('audio_duration') is not None:
        if not positive(data['audio_duration']) or data['audio_duration'] > duration + .1:
            errors.append('Invalid source narration duration or narration longer than video timeline.')
    return scenes


def check_media(args, data, scenes, report):
    import av
    import numpy as np
    samples = {}
    targets = [(i, s['start'] + (s['end']-s['start'])*.65) for i,s in enumerate(scenes)]
    motion = [[] for _ in scenes]
    count = 0
    previous = None
    previous_scene = None
    scene_index = 0
    previous_time = -1
    with av.open(str(args.video)) as container:
        if not container.streams.video or not container.streams.audio:
            raise ValueError('MP4 must contain both video and audio streams.')
        stream = container.streams.video[0]
        width, height = stream.width, stream.height
        fps = float(stream.average_rate or 0)
        if fps <= 0:
            raise ValueError('No usable video frame rate.')
        step = max(1, round(fps / 5))
        for frame in container.decode(video=0):
            if frame.time is None:
                raise ValueError('Video frame is missing its timestamp.')
            t = float(frame.time)
            if t <= previous_time:
                raise ValueError('Video timestamps are not increasing.')
            previous_time = t
            count += 1
            while targets and t >= targets[0][1]:
                index, target = targets.pop(0)
                samples[index] = (t, frame.to_image()) if args.contact_sheet else (t, None)
            while scene_index < len(scenes)-1 and t >= scenes[scene_index]['end']:
                scene_index += 1
            if count % step == 0:
                # Configurable normalized ROI excludes title/caption/progress by default.
                arr = frame.reformat(width=180, height=320, format='rgb24').to_ndarray()
                x0,y0,x1,y1 = args.motion_roi
                crop = arr[int(y0*320):int(y1*320),int(x0*180):int(x1*180)].astype('float32')
                # Exclude transitions and samples across scenes from the motion estimate.
                scene = scenes[scene_index]
                inside = scene['start']+.5 < t < scene['end']-.4
                if previous is not None and previous_scene == scene_index and inside:
                    motion[scene_index].append(float(np.abs(crop-previous).mean()))
                previous, previous_scene = crop, scene_index
        if not count:
            raise ValueError('No decoded video frames.')
        video_end = previous_time + 1/fps
    report.update(size=[width,height], fps=fps, frames_decoded=count, video_duration=video_end,
                  scene_samples=[{'scene':i+1,'time':v[0]} for i,v in samples.items()],motion_roi=args.motion_roi)
    tolerance = max(.1, 2/fps)
    if abs(video_end-data['duration']) > tolerance:
        report['errors'].append('Encoded video duration differs from timeline.')
    if abs(count/fps-video_end) > tolerance:
        report['errors'].append('Frame count/timestamps inconsistent with constant frame rate.')
    for attr, actual in [('width',width),('height',height),('fps',fps)]:
        expected = getattr(args, attr)
        if expected is not None and abs(actual-expected) > .05:
            report['errors'].append(f'Unexpected {attr}: {actual}; expected {expected}.')
    if targets:
        report['errors'].append('Not every scene could be sampled from the actual MP4.')
    peak, total, clipped, audible_start, audible_end = 0., 0, 0, None, None
    first_pts, last_pts, prior_end = None, None, None
    timestamp_gaps = 0
    with av.open(str(args.video)) as container:
        resampler = av.AudioResampler(format='fltp', layout='mono', rate=24000)
        def consume(frame):
            nonlocal peak,total,clipped,audible_start,audible_end
            array = frame.to_ndarray().ravel()
            if not np.isfinite(array).all():
                raise ValueError('Audio contains non-finite samples.')
            if len(array):
                peak = max(peak,float(np.abs(array).max()))
                clipped += int((np.abs(array) >= .999).sum())
                audible = np.flatnonzero(np.abs(array) > .015)
                if len(audible):
                    if audible_start is None: audible_start = (total+int(audible[0]))/24000
                    audible_end = (total+int(audible[-1]))/24000
                total += len(array)
        for frame in container.decode(audio=0):
            if frame.time is None:
                raise ValueError('Audio frame is missing its timestamp.')
            now = float(frame.time)
            if first_pts is None: first_pts = now
            if prior_end is not None and abs(now-prior_end) > .1: timestamp_gaps += 1
            last_pts = now+frame.samples/frame.sample_rate
            prior_end = last_pts
            for converted in resampler.resample(frame): consume(converted)
        for converted in resampler.resample(None): consume(converted)
    if not total or audible_start is None:
        report['errors'].append('No audible narration detected.')
    if first_pts is not None and (abs(first_pts) > tolerance or abs(last_pts-video_end) > tolerance or timestamp_gaps):
        report['errors'].append('Audio timestamps do not cover video or have gaps.')
    if abs(total/24000-video_end) > tolerance:
        report['errors'].append('Decoded audio length differs from video; mux silence for intentional tail hold.')
    if peak >= 1.0:
        report['errors'].append('Audio reaches/exceeds full scale; review clipping.')
    if clipped:
        report['warnings'].append('Near-full-scale samples detected; listen for clipping.')
    report.update(audio_duration=total/24000,audio_peak=peak,near_full_scale_samples=clipped,
                  audible_span=[audible_start,audible_end],audio_timestamp_start=first_pts,audio_timestamp_end=last_pts)
    report['art_motion'] = [{'scene':i+1,'max_mean_change':max(values,default=0)} for i,values in enumerate(motion)]
    for item in report['art_motion']:
        if item['max_mean_change'] < .1:
            report['warnings'].append(f"Scene {item['scene']}: little ROI motion detected; review content and ROI manually.")
    if args.contact_sheet and samples:
        from PIL import Image, ImageDraw
        columns = min(4,len(samples))
        thumb_w = 216
        thumb_h = round(thumb_w*height/width)
        cell_h = thumb_h+28
        sheet = Image.new('RGB',(columns*thumb_w, math.ceil(len(samples)/columns)*cell_h),'#F8F6EF')
        draw = ImageDraw.Draw(sheet)
        for i,(timestamp,frame_image) in samples.items():
            x,y = (i%columns)*thumb_w,(i//columns)*cell_h
            sheet.paste(frame_image.resize((thumb_w,thumb_h)),(x,y))
            draw.text((x+6,y+thumb_h+5),f'Scene {i+1} / {timestamp:.2f}s',fill='black')
        args.contact_sheet.parent.mkdir(parents=True,exist_ok=True)
        sheet.save(args.contact_sheet)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline',type=Path,required=True)
    parser.add_argument('--video',type=Path)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--contact-sheet',type=Path)
    parser.add_argument('--timeline-only',action='store_true')
    parser.add_argument('--width',type=int)
    parser.add_argument('--height',type=int)
    parser.add_argument('--fps',type=float)
    parser.add_argument('--motion-roi',type=float,nargs=4,default=[0,.23,1,.74],metavar=('X0','Y0','X1','Y1'))
    args = parser.parse_args()
    report = {'errors':[],'warnings':[], 'checks_scope':'Timeline only' if args.timeline_only else 'Decoded media and timeline',
              'human_review_required':True,'limitations':'No ASR, pronunciation, semantic synchronization or visual quality acceptance. Motion statistics do not prove independent element animation.'}
    try:
        if not args.timeline_only and not args.video: raise ValueError('--video is required unless --timeline-only.')
        x0,y0,x1,y1 = args.motion_roi
        if not (0<=x0<x1<=1 and 0<=y0<y1<=1 and (x1-x0)*180>=1 and (y1-y0)*320>=1):
            raise ValueError('Motion ROI must have nonempty normalized bounds.')
        sources = [args.timeline] + ([args.video] if args.video else [])
        destinations = [args.report] + ([args.contact_sheet] if args.contact_sheet else [])
        if len({p.resolve() for p in destinations}) != len(destinations) or any(p.resolve()==s.resolve() for p in destinations for s in sources):
            raise ValueError('Report/contact sheet paths must differ from each other and input files.')
        data = json.loads(args.timeline.read_text(encoding='utf-8-sig'))
        scenes = check_timeline(data,report)
        report['alignment'] = data.get('alignment')
        if not args.timeline_only and not report['errors']: check_media(args,data,scenes,report)
    except Exception as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}')
    report['automated_checks_passed'] = not report['errors']
    # Refuse to overwrite a source even when argument validation failed.
    if args.report.resolve() not in {p.resolve() for p in [args.timeline,args.video] if p}:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['automated_checks_passed','errors','warnings']},ensure_ascii=False))
    return 0 if report['automated_checks_passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
