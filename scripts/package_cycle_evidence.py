"""Package only listed research artifacts; never traverse market data/holdout."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from cryptoquant.data.archive import sha_file


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-root',type=Path,required=True)
    args=parser.parse_args()
    root=Path.cwd()
    source=args.source_root.resolve()
    output=root/'artifacts/research'
    archive=output/'phase-a-and-tenth-evidence.zip'
    paths={}
    for number in (*range(159,186),192):
        folder=root/f'artifacts/experiments/EXP-{number}'
        for path in folder.rglob('*'):
            if path.is_file():
                paths[path.relative_to(root).as_posix()]=path
    # Frozen pre-repair inputs and their snapshots, no raw market directories.
    for number in (108,109,110,133,134,135,*range(141,150)):
        folder=source/f'artifacts/experiments/EXP-{number}'
        for path in folder.rglob('*'):
            if path.is_file():
                paths[path.relative_to(source).as_posix()]=path
    for name in ('state_W1.parquet','state_W2.parquet','state_R2025.parquet',
                 'state_manifest.json','run_manifest.json','source_manifest.json','config.toml','research_config.toml'):
        path=source/'artifacts/experiments/EXP-122'/name
        paths[path.relative_to(source).as_posix()]=path
    for path in output.glob('R6_*_closed_cycles.csv'):
        paths[path.relative_to(root).as_posix()]=path
    for path in paths.values():
        assert path.relative_to(root if path.is_relative_to(root) else source).parts[0]=='artifacts'
        assert path.suffix not in ('.env','.pem','.key')
    hashes={name:sha_file(path) for name,path in paths.items()}
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as bundle:
        for name,path in sorted(paths.items()):
            bundle.write(path,name)
    with zipfile.ZipFile(archive) as bundle:
        assert set(bundle.namelist())==set(hashes)
        for name,value in hashes.items():
            assert hashlib.sha256(bundle.read(name)).hexdigest()==value,name
    manifest=dict(archive=archive.name,sha256=sha_file(archive),size_bytes=archive.stat().st_size,
                  file_count=len(hashes),files=hashes,holdout_included=False,
                  raw_market_data_included=False,
                  note='Extract at repository root; files match immutable byte hashes. Original data partitions require separate rebuild and hash verification.')
    (output/'evidence_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Archive verified:',len(hashes),'files,',round(archive.stat().st_size/1024**2,2),'MiB, SHA256:',manifest['sha256'])


if __name__=='__main__':
    main()
