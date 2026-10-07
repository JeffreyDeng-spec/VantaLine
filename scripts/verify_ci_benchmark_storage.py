"""Inspect two synthetic CI databases without relaxing PostgreSQL write settings."""
import json
import os
import subprocess

NORMAL_DSN='postgresql://vantaline:vantaline_ci@127.0.0.1:5432/vantaline'
BENCHMARK_DSN='postgresql://vantaline:vantaline_ci@127.0.0.1:5433/vantaline'


def inspect_database(dsn):
    import psycopg
    with psycopg.connect(dsn,autocommit=True) as connection:
        settings={key:connection.execute('SELECT current_setting(%s)',(key,)).fetchone()[0]
                  for key in ['server_version_num','data_directory','fsync','synchronous_commit',
                              'full_page_writes','temp_tablespaces','max_wal_size','shared_buffers']}
        print(json.dumps({'stage':'database_settings','settings':settings}),flush=True)
        assert int(settings['server_version_num'])//10000==16
        for key in ['fsync','synchronous_commit','full_page_writes']:assert settings[key]=='on',(key,settings[key])
        assert settings['data_directory']=='/var/lib/postgresql/data'
        assert not settings['temp_tablespaces']
        tablespaces=connection.execute('SELECT spcname,pg_tablespace_location(oid) FROM pg_tablespace ORDER BY spcname').fetchall()
        assert tablespaces==[('pg_default',''),('pg_global','')],tablespaces
        identity=connection.execute('SELECT system_identifier::text FROM pg_control_system()').fetchone()[0]
        size=connection.execute('SELECT pg_database_size(current_database())').fetchone()[0]
    return dict(system_identifier=identity,settings=settings,tablespaces=tablespaces,database_bytes=size)


def inspect_container(identifier):
    # Select metadata only. Never dump container environment/credentials.
    raw=subprocess.check_output(['docker','inspect','--format',
        '{{json .HostConfig.Tmpfs}}|{{.HostConfig.Memory}}|{{.HostConfig.MemorySwap}}|{{.State.OOMKilled}}',identifier],text=True).strip()
    tmpfs,memory,swap,oom=raw.split('|')
    print(json.dumps({'stage':'container_configuration','tmpfs':json.loads(tmpfs),'memory_limit_bytes':int(memory),'memory_swap_limit_bytes':int(swap),'oom_killed':oom}),flush=True)
    assert json.loads(tmpfs)=={'/var/lib/postgresql/data':'rw,noexec,nosuid,size=2147483648'}
    assert int(memory)==3221225472 and int(swap)==3221225472 and oom=='false'
    shell='''test "$(stat -f -c %T /var/lib/postgresql/data)" = tmpfs
test "$(readlink -f /var/lib/postgresql/data/pg_wal)" = /var/lib/postgresql/data/pg_wal
echo FILESYSTEM_BYTES
df -B1 --output=size,used,avail /var/lib/postgresql/data
du -sb /var/lib/postgresql/data
echo MEMORY_PEAK_BYTES
cat /sys/fs/cgroup/memory.peak
echo MEMORY_MAX_BYTES
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/memory.swap.max'''
    try:
        output=subprocess.check_output(['docker','exec',identifier,'sh','-ec',shell],text=True)
    except subprocess.CalledProcessError as error:
        print(json.dumps({'stage':'container_storage_partial_evidence','output':error.output}),flush=True)
        raise
    print(json.dumps({'stage':'container_storage_evidence','output':output}),flush=True)
    lines=output.splitlines()
    events={line.split()[0]:int(line.split()[1]) for line in lines if line.split() and line.split()[0] in ['max','oom','oom_kill','oom_group_kill']}
    assert {'max','oom','oom_kill'}<=events.keys(),events
    assert all(value==0 for value in events.values()),events
    capacity,used,available=map(int,lines[lines.index('FILESYSTEM_BYTES')+2].split())
    assert capacity==2147483648,(capacity,used,available)
    assert 0<=used<=capacity and 0<=available<=capacity
    actual_memory=int(lines[lines.index('MEMORY_MAX_BYTES')+1])
    assert actual_memory==int(memory),actual_memory
    peak=int(lines[lines.index('MEMORY_PEAK_BYTES')+1]);assert 0<peak<=actual_memory
    assert lines[-1]=='0','benchmark container swap is not disabled'
    return dict(tmpfs=json.loads(tmpfs),memory_limit_bytes=int(memory),memory_swap_limit_bytes=int(swap),
                oom_killed=False,filesystem_capacity_bytes=capacity,filesystem_used_bytes=used,filesystem_available_bytes=available,actual_memory_limit_bytes=actual_memory,container_peak_memory_bytes=peak,mount_wal_capacity_and_cgroup_evidence=output)


def inspect_ordinary_container(identifier):
    raw=subprocess.check_output(['docker','inspect','--format',
        '{{json .HostConfig.Tmpfs}}|{{.State.OOMKilled}}',identifier],text=True).strip()
    tmpfs,oom=raw.split('|')
    output=subprocess.check_output(['docker','exec',identifier,'sh','-ec',
        'stat -f -c %T /var/lib/postgresql/data; readlink -f /var/lib/postgresql/data/pg_wal'],text=True)
    print(json.dumps({'stage':'ordinary_storage_evidence','tmpfs':json.loads(tmpfs),'oom_killed':oom,'output':output}),flush=True)
    assert not json.loads(tmpfs) and oom=='false'
    lines=output.splitlines()
    assert len(lines)==2 and lines[0]!='tmpfs'
    assert lines[1]=='/var/lib/postgresql/data/pg_wal'
    return dict(tmpfs=json.loads(tmpfs),filesystem_type=lines[0],wal_path=lines[1],oom_killed=False)


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true','synthetic CI verification only'
    assert os.environ['VANTALINE_POSTGRES_DSN']==NORMAL_DSN
    assert os.environ['VANTALINE_BENCHMARK_POSTGRES_DSN']==BENCHMARK_DSN
    ordinary_storage=inspect_ordinary_container(os.environ['VANTALINE_ORDINARY_CONTAINER'])
    container=inspect_container(os.environ['VANTALINE_BENCHMARK_CONTAINER'])
    normal=inspect_database(NORMAL_DSN);benchmark=inspect_database(BENCHMARK_DSN)
    assert normal['system_identifier']!=benchmark['system_identifier'],'benchmarks must use a separate instance'
    print(json.dumps(dict(scope='Bounded tmpfs endpoint-relative benchmark; includes persisted pagination snapshot writes, not production physical-storage P95/durability evidence',
        ordinary_disk_database=normal,ordinary_storage=ordinary_storage,benchmark_database=benchmark,container=container),sort_keys=True))


if __name__=='__main__':main()
