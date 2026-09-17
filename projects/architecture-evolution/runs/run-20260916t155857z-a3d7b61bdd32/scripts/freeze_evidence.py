"""固定本轮最终源码与已有证据；不包含仍在追加的文稿收口回执。"""
from pathlib import Path
import sys,json,hashlib,zipfile,subprocess
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT/'automation/scripts'))
import deployment
run=Path(__file__).resolve().parents[1]
out=run/'verification'
out.mkdir(exist_ok=True)
files=sorted(set(deployment.framework_files(ROOT)+['.gitignore']))
manifest={}
with zipfile.ZipFile(out/'source-snapshot.zip','x',zipfile.ZIP_DEFLATED) as z:
    for name in files:
        data=(ROOT/name).read_bytes()
        manifest[name]=hashlib.sha256(data).hexdigest()
        z.writestr(name,data)
(out/'source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'reading-note-r5.md').write_bytes((ROOT/'context/reading-notes/RS-47e7e8ce-9f60-4fd0-af4d-a7580a69cb04/current.md').read_bytes())
# 测试日志逐文件固化为ZIP，避免后续收口回执成为自引用输入。
with zipfile.ZipFile(out/'test-evidence.zip','x',zipfile.ZIP_DEFLATED) as z:
    for area in ['backend','frontend','home','release-checks','catalog']:
        for p in sorted((run/'.run-captures'/area).rglob('*')):
            if p.is_file(): z.write(p,p.relative_to(run).as_posix())
meta=json.loads((run/'run.json').read_text(encoding='utf-8-sig'))
meta.update(status='failed',ended_at=datetime.now(timezone.utc).isoformat(),question='如何使当前阅读笔记可发现、可读并关联定向证据，同时保护私人数据及旧工作区？',metrics={'backend_passed':31,'component_passed':17,'browser_passed':5,'browser_failed':1,'deployment_unique_passed':19,'real_list_seconds':20.266},quality_results=[{'name':'targeted_reading_and_upgrade_checks','status':'passed'},{'name':'browser_scale_N0','status':'failed','detail':'既有规模场景60秒定位超时；其余5项通过'}],conclusion='阅读上下文、首页与主题导航修复已验证；完整浏览器选择仍含既有失败。',limitations=['列表逐会话核验来源仍较慢','既有规模N0超时未修复','未验证第二台物理机','AI一致性自查不等于科学复核'])
(run/'run.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
cmd=[sys.executable,str(ROOT/'automation/scripts/workspace_cli.py'),'run-register',meta['run_id']]
for name in ['source-snapshot.zip','source-manifest.json']:cmd+=['--input',str(out/name)]
for p in [run/'RESULTS.md',out/'test-evidence.zip',out/'reading-note-r5.md']:cmd+=['--artifact',str(p)]
result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
(out/'registration.json').write_text(result.stdout,encoding='utf-8')
print(result.stdout);print(result.stderr);sys.exit(result.returncode)
