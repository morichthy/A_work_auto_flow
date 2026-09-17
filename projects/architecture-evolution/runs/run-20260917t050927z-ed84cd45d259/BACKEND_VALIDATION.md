# v0.4.0 后端完整回归

源码起点为 948b8ad；未修改产品代码、测试代码或冻结夹具。使用现有 `automation/python.ps1 -m unittest discover -s automation/tests -v`。

最终按实际 discovery 的 ID 去重，745/745 项均有终态：744 通过、1 失败、0 error、0 skip、0 未覆盖。详见 `backend-coverage-ledger.json` 与 `discovered-backend-test-ids.json`。这不是全绿回归。

首次运行在 694 项有终态后，停在 `test_workbench_relations.RelationsTests.test_authorization_change_invalidates_cached_projection` 的准备阶段。项目 tmp 目录单次 mkdir 探测明确返回 PermissionError WinError5，与 v0.3 的 tempfile 重试故障一致。受控停止本次测试 Python PID 65956；未触及正式工作台进程。首轮未完成用例不计为通过。原日志、非零退出码和探测见 `backend-unittest.log`、`backend-unittest.exitcode`、`tmp-single-mkdir-probe.log`。

随后仅提升权限续跑尚未完成的 `test_w*.py` 四模块共 51 项，11.602 秒全部通过；见 `backend-unittest-resume.log` 及退出码。没有重复运行已通过项。

唯一失败是 `test_memory_fixture.MemoryFixtureTests.test_b01_frozen_plan_self_test_leaves_assets_unchanged`。独立复验同样失败，完整 trace 位于 `backend-b01-recheck.log`：`automation/tests/test_memory_fixture.py:50` 对 `module.main(["--self-test"])` 的 0 断言得到 1；报告错误为 `fixture manifest mismatch: 输入或数量与冻结清单不同`。

数量与冻结清单全部一致，实际差异为 records.json、acceptance.json、work-packages.json 的字节 SHA256；精确期望和实际值在覆盖账本中。三文件以及 fixture-manifest.json 均与 v0.3.0 分发源码逐字节相同，见 `b01-v030-comparison.json`。未重写历史夹具来消除既有失败。

测试目录的 745 Python 用例与跨栈目录数不同：catalog 的 857 条由 745 Python、85 component、25 browser、1 check、1 integration 组成。此报告仅声明 Python 后端覆盖；不把其它栈计入已执行数。真实部署/升级19项、离线模型及384维实际向量测试均包含在本次后端通过结果中；不等价于第二物理机或真实业务验收。
