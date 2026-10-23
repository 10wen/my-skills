# Security policy

Do not open a public issue containing API keys, tokens, cookies, signed URLs, private media or local absolute paths. Revoke or rotate an exposed credential first, then contact the maintainer through a private GitHub security advisory if available.

The repository reads optional credentials from environment variables or OS-protected storage and must never print their values. Generated project folders, logs and ZIP files should be scanned before sharing. Security reports should include the affected file and reproduction steps, with secrets replaced by placeholders.
