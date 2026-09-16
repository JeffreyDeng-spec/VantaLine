#!/usr/bin/env python3
"""Allow multipart overhead on the VantaLine upstream; preserve all other sites."""
import re
import subprocess
from pathlib import Path


def main():
    changed = {}
    try:
        for link in Path('/etc/nginx/sites-enabled').iterdir():
            path = link.resolve()
            source = path.read_text()
            if not re.search(r'proxy_pass\s+http://(?:127\.0\.0\.1|localhost):8765\b', source):
                continue
            updated = re.sub(r'(client_max_body_size\s+)200m(\s*;)', r'\g<1>201m\2', source)
            if updated != source:
                changed[path] = source
                path.write_text(updated)
        subprocess.run(['nginx', '-t'], check=True)
        if changed:
            subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
    except Exception:
        for path, source in changed.items():
            path.write_text(source)
        raise
    print(f'PDF multipart allowance: {len(changed)} site files updated')


if __name__ == '__main__':
    main()
