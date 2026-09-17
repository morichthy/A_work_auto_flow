"""通过真实脚本进程验证登记入口、预览和用户 Skill 冲突保护。

使用隔离的中文/空格工作区复制安装器和受控 workflow，不操作开发工作区
的 .agents。文件字节和目录集合同时比较，避免把空目录残留当作未写入。
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "automation/scripts"))
import deployment
import install_workspace_skills as installer


class WorkspaceSkillInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="workspace-skills-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "合成 旧工作区"
        self.script = self.root / "automation/scripts/install_workspace_skills.py"
        self.script.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "automation/scripts/install_workspace_skills.py", self.script)
        for name in installer.NAMES + installer.COMPAT_NAMES:
            target = self.root / "automation/workflows" / name / "SKILL.md"
            target.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / "automation/workflows" / name / "SKILL.md", target)

    def run_install(self, *arguments, expected=0):
        result = subprocess.run([sys.executable, str(self.script), *arguments], cwd=self.root,
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def snapshot(self):
        return ({path.relative_to(self.root).as_posix(): path.read_bytes()
                 for path in self.root.rglob("*") if path.is_file()},
                {path.relative_to(self.root).as_posix() for path in self.root.rglob("*") if path.is_dir()})

    def custom(self, name, content):
        target = self.root / ".agents/skills" / name / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def test_default_preview_four_entries_install_and_repeat_preserve_extra_skill(self):
        self.assertEqual(installer.NAMES, ("work-loop", "context-maintenance", "evidence-inspection", "development-checks",
                                         "material-query", "association-exploration", "semantic-maintenance", "consolidate-results"))
        custom = self.custom("用户 自定义", b"private custom skill\r\n")
        before = self.snapshot()
        self.run_install()
        self.assertEqual(self.snapshot(), before)
        self.run_install("--apply")
        for name in installer.NAMES:
            text = (self.root / ".agents/skills" / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("name: " + name, text)
            self.assertIn("../../../automation/workflows/" + name + "/SKILL.md", text)
        self.assertEqual(custom.read_bytes(), b"private custom skill\r\n")
        installed = self.snapshot()
        self.run_install("--apply")
        self.assertEqual(self.snapshot(), installed)

    def test_last_entry_conflict_rejects_whole_batch_before_any_write(self):
        # 批次中一项发生冲突：其他项也不得创建文件或目录。
        self.custom("work-loop", b"user-owned research skill\r\n")
        self.custom("用户 自定义", b"unrelated local tool")
        before = self.snapshot()
        preview = self.run_install(expected=2)
        self.assertIn("-user-owned research skill", preview.stderr)
        self.assertIn("+name: work-loop", preview.stderr)
        self.assertIn("(current, preserved)", preview.stderr)
        self.assertIn("(generated proposal)", preview.stderr)
        self.assertEqual(self.snapshot(), before)
        applied = self.run_install("--apply", expected=2)
        self.assertIn("-user-owned research skill", applied.stderr)
        self.assertIn("+name: work-loop", applied.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_name_selection_preserves_other_modified_skills_and_is_idempotent(self):
        custom = self.custom("workspace-context", b"modified existing default")
        extra = self.custom("用户 自定义", b"keep this extra skill")
        self.run_install("--name", "work-loop", "--name", "work-loop", "--apply")
        self.assertEqual(custom.read_bytes(), b"modified existing default")
        self.assertEqual(extra.read_bytes(), b"keep this extra skill")
        self.assertFalse((self.root / ".agents/skills/context-maintenance").exists())
        self.assertFalse((self.root / ".agents/skills/evidence-inspection").exists())
        before = self.snapshot()
        self.run_install("--name", "work-loop", "--apply")
        self.assertEqual(self.snapshot(), before)

    def test_managed_migration_is_fingerprinted_backed_up_and_reversible(self):
        import upgrade_fixture
        legacy = self.custom('research-loop', upgrade_fixture.legacy_skill('research-loop').encode())
        old = legacy.read_bytes()
        changed = self.custom('material-query', (upgrade_fixture.legacy_skill('material-query') + '用户附加约束').encode())
        original = changed.read_bytes()
        entries = installer.managed_updates(self.root, self.root)
        self.assertEqual([item['path'] for item in entries], ['.agents/skills/research-loop/SKILL.md'])
        self.assertEqual(legacy.read_bytes(), old)
        backup = deployment.apply_upgrade(self.root, self.root, entries)
        self.assertFalse(legacy.exists())
        self.assertEqual(changed.read_bytes(), original)
        deployment.rollback(backup)
        self.assertEqual(legacy.read_bytes(), old)
        self.assertEqual(changed.read_bytes(), original)

    def test_retired_names_cannot_be_installed(self):
        before = self.snapshot()
        self.run_install("--name", "research-loop", "--apply", expected=2)
        self.assertEqual(self.snapshot(), before)

    def test_public_archive_missing_local_state_is_seeded_without_overwrite(self):
        # First-install defaults use the same recoverable write transaction;
        # repeated setup and upgrades must retain subsequently entered user state.
        entries = deployment.plan(self.root, self.root)
        self.assertEqual({e['path'] for e in entries},
                         {'retrieval/sources.json', 'context/NOW.md'})
        backup = deployment.apply_upgrade(self.root, self.root, entries)
        source = self.root / 'retrieval/sources.json'
        self.assertIn('"sources": []', source.read_text())
        source.write_text('{"schema_version":1,"sources":[{"path":"user"}]}')
        self.assertEqual(deployment.plan(self.root, self.root), [])
        # Restore only after reverting the simulated user edit to expected bytes.
        source.write_bytes(b'{"schema_version": 1, "sources": []}\n')
        deployment.rollback(backup)
        self.assertFalse(source.exists())

    def test_release_framework_inventory_includes_each_workflow_and_installer(self):
        # 调用真实发布清单函数，证明目录扫描包含新 workflow；用户入口
        # 是 seed 内容，不能进入可替换框架集合。
        self.custom("用户 自定义", b"not framework content")
        included = deployment.framework_files(self.root)
        self.assertIn("automation/scripts/install_workspace_skills.py", included)
        for name in installer.NAMES:
            self.assertIn("automation/workflows/" + name + "/SKILL.md", included)
        self.assertFalse(any(name.startswith(".agents/") for name in included))


if __name__ == "__main__":
    unittest.main()
