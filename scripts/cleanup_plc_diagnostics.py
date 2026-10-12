#!/usr/bin/env python3
"""Low-priority bounded expiry of the independent diagnostic table only."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.storage.plc_diagnostic_repository import PlcDiagnosticRepository

async def cleanup(environment):
    repository=PlcDiagnosticRepository(environment)
    total=0
    for _ in range(50):
        try: count=await repository.cleanup()
        except Exception:
            print('PLC diagnostic cleanup unavailable; production state unchanged')
            return 1
        total+=count
        if count<500:break
        await asyncio.sleep(.2)
    print(f'PLC diagnostic expired rows removed: {total}')
    return 0

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--runtime-config',type=Path)
    args=parser.parse_args();environment=dict(os.environ)
    if args.runtime_config:
        environment.update(json.loads(args.runtime_config.read_text())['environment'])
        if os.getuid()==0:
            import pwd
            account=pwd.getpwnam('vantaline');os.setgroups([]);os.setgid(account.pw_gid);os.setuid(account.pw_uid)
    return asyncio.run(cleanup(environment))
if __name__=='__main__':raise SystemExit(main())
