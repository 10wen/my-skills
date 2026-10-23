"""Local capability checks. Never calls a paid API or installs dependencies."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--mode', choices=['render', 'asr', 'all'], default='render')
    parser.add_argument('--audio', type=Path, help='Authorized local audio; only its first five seconds are transcribed')
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding='utf-8-sig'))
    checks = []
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8', HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')

    def record(name, passed, detail):
        checks.append(dict(check=name, passed=bool(passed), detail=detail))

    def path(key):
        value = cfg.get(key)
        if not value or not Path(value).is_file():
            record(key, False, 'Missing file; configure an existing executable or CLI entrypoint.')
            return None
        return str(Path(value).resolve())

    def run(name, command, timeout=45):
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, timeout=timeout)
            # Do not echo arbitrary subprocess logs, user text or environment values.
            ok = result.returncode == 0
            record(name, ok, 'Executed successfully.' if ok else 'Subprocess failed, exit=' + str(result.returncode) + '; do not retry unchanged runtime.')
            return result if ok else None
        except subprocess.TimeoutExpired:
            record(name, False, 'Timed out; do not repeat unchanged command.')
        except OSError as exc:
            record(name, False, 'Could not start process: ' + type(exc).__name__)
        return None

    if args.mode in ['render', 'all']:
        ffmpeg, ffprobe, node, cli, chrome = [path(k) for k in ['ffmpeg', 'ffprobe', 'node', 'hyperframes_cli', 'chrome']]
        if ffmpeg and ffprobe:
            with tempfile.TemporaryDirectory(prefix='handdrawn-preflight-') as tmp:
                video = str(Path(tmp) / 'encoder-check.mp4')
                if run('h264_actual_encode', [ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'color=c=white:s=64x64:r=30', '-frames:v', '3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', video]):
                    r = run('ffprobe_actual_media', [ffprobe, '-v', 'error', '-show_entries', 'stream=codec_name,width,height', '-of', 'json', video])
                    if r:
                        streams = json.loads(r.stdout).get('streams', [])
                        record('h264_probe_matches', any(s.get('codec_name') == 'h264' and s.get('width') == 64 and s.get('height') == 64 for s in streams), 'Expected H.264, 64x64.')
        if node and cli:
            run('hyperframes_cli', [node, cli, '--help'])
        if node and cli and chrome:
            code = """const {createRequire}=require('node:module');
const req=createRequire(process.argv[1]);
(async()=>{const p=req('puppeteer-core');const b=await p.launch({executablePath:process.argv[2],headless:true,args:['--disable-gpu']});
try{const page=await b.newPage();await page.setViewport({width:64,height:64});await page.setContent('<svg width="64" height="64"><rect width="64" height="64" fill="blue"/></svg>');const png=await page.screenshot();if(png.length<100)throw Error('empty screenshot');}finally{await b.close();}})().catch(()=>process.exit(1));"""
            run('chrome_actual_capture_and_puppeteer_dependency', [node, '-e', code, cli, chrome])
        media_python = path('media_python')
        if media_python:
            run('media_qa_imports', [media_python, '-c', 'import av,numpy; from PIL import Image; print("ok")'])

    if args.mode in ['asr', 'all']:
        asr_python = path('asr_python')
        model = Path(cfg['asr_model']) if cfg.get('asr_model') else None
        required = ['model.bin', 'config.json', 'tokenizer.json']
        ready = model is not None and all((model / f).is_file() and (model / f).stat().st_size > 0 for f in required)
        record('asr_model_files', ready, 'Require nonempty model.bin, config.json, tokenizer.json; a cache directory alone is insufficient.')
        if ready and asr_python:
            audio = args.audio.resolve() if args.audio else None
            if audio and not audio.is_file():
                record('asr_audio_sample', False, 'Specified local audio does not exist.')
            else:
                code = """import sys
import numpy as np
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio
m=WhisperModel(sys.argv[1],device='cpu',compute_type='int8',cpu_threads=2,local_files_only=True)
sample=decode_audio(sys.argv[2],sampling_rate=16000)[:80000] if len(sys.argv)>2 else np.zeros(16000,dtype=np.float32)
segs,_=m.transcribe(sample,language='zh',beam_size=1,vad_filter=False,condition_on_previous_text=False)
count=sum(1 for _ in segs)
if len(sys.argv)>2 and count==0:raise RuntimeError('No speech segments from supplied sample')
print('smoke_completed')
"""
                cmd = [asr_python, '-c', code, str(model.resolve())] + ([str(audio)] if audio else [])
                run('asr_model_load_and_inference', cmd, timeout=120)

    report = dict(passed=bool(checks) and all(c['passed'] for c in checks), mode=args.mode, paid_requests=0, model_downloads=0, checks=checks,
                  scope='Local execution checks only; not speech naturalness, full scene layout or service availability. Required checks depend on the chosen route.')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
