# 脚本说明

这里放本地开发和测试脚本。

## 文件

- `start-dev.ps1`：后台启动后端和前端，健康检查与 API 代理检查通过后才报告成功。
- `start-backend.ps1`：单独后台启动并登记后端。
- `start-frontend.ps1`：单独后台启动并登记前端；支持 `-Preview` 启动构建预览。
- `stop-dev.ps1`：只停止已登记且 PID、启动时间、可执行文件和项目路径匹配的进程；不按端口杀进程。
- `dev-common.ps1`：共享配置、解释器选择、启动锁、进程记录与就绪检查。
- `check-env.py`：只读检查后端依赖和配置；不写库、不调用模型、不输出密钥。
- `test_dev_lifecycle.py`：使用临时库、临时日志与临时端口验证 Windows 启停流程，需已安装前端依赖并完成构建。
- `test-backend.ps1`：运行隔离的后端离线测试，支持 `-Python` 指定解释器，并透传测试退出码。
- `check.ps1`：依次运行后端测试、前端类型检查和生产构建；任何阶段失败即返回非零退出码。
- `data_tools.py`：创建一致性备份、校验、恢复到新路径、生成旧会话与小说索引；只依赖 Python 标准库。

## 常用命令

首次配置（已有 `config.local.ps1` 时不要覆盖）：

```powershell
Copy-Item config.example.ps1 config.local.ps1
```

编辑本地文件中的端口、可选解释器、模型变量。启动和测试脚本会加载它，其赋值覆盖继承的
环境变量；`-NoLocalConfig` 可跳过加载。配置文件是本地 PowerShell 脚本，不读取不可信来源。
真实密钥不提交 Git，禁止使用 `VITE_*` 存放密钥。无需配置模型也可以启动本地兜底模式。

Python 选择顺序为：`-Python` 参数 → `CAMPUS_PYTHON` → 项目 `.venv\Scripts\python.exe`
→ PATH 中第一个 `python`，不再依赖固定 Miniconda 路径。启动和后端测试使用同一套规则。

默认端口为后端 8766、开发前端 5176、预览前端 4176，均仅监听 127.0.0.1。
对应配置为 `CAMPUS_BACKEND_PORT`、`CAMPUS_FRONTEND_PORT`、`CAMPUS_PREVIEW_PORT`。
端口占用时启动失败，不自动换端口、不停止原有进程。`CAMPUS_DB_PATH` 可选择独立数据库，
相对路径从项目根目录解析；默认仍为 `data/campus_lite.db`。

直接运行 Python 或 npm 不自动加载 PowerShell 配置。如需使用本地配置，先在同一终端执行
`. .\config.local.ps1`。直接运行 `python backend/run.py` / `npm run dev` 的进程没有登记，
请在原终端用 Ctrl+C 停止；停止脚本不会接管这些进程。

数据备份：

```powershell
python scripts/data_tools.py backup
```

默认备份保存在 `data/backups/`，不会写入正式数据库。`verify` 与 `inventory` 只读；
`restore` 只创建新路径中的副本，拒绝覆盖文件。完整命令和旧数据找回说明见
[data/README.md](../data/README.md)。备份、恢复副本和私人索引不纳入 Git。
如果修改了数据库位置，先加载本地配置，或给备份和索引命令显式传入 `--database`。

运行项目统一检查：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check.ps1
```

指定 Python：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check.ps1 -Python "D:\APP\miniconda3\python.exe"
```

统一检查不启动或停止服务，不调用真实模型接口。后端测试只在临时目录创建数据库，
结束后清理；前端构建会更新被 Git 忽略的 `frontend/dist/`。请先安装项目依赖。

启动本地开发环境：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

停止本地开发环境：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\stop-dev.ps1
```

仅停止前端或预演停止：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\stop-dev.ps1 -Services frontend
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\stop-dev.ps1 -WhatIf
```

进程记录在 `runtime/dev-processes.json`，新日志按每次启动分组，保存到
`runtime/logs/<时间-标识>/` 下的 `backend.out.log`、`backend.err.log`、
`frontend.out.log`、`frontend.err.log`。Vite 缓存也移到 `runtime/vite-cache/`。
这些内容不提交 Git；根目录已有旧日志保留。运行期间不要删除进程记录。
启动失败会停止本次已经启动的服务；无法确认身份的进程会保留记录并报告，不强行终止。

运行后端全量测试：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test-backend.ps1
```

运行前端构建：

```powershell
cd frontend
npm run build
```

构建后启动完整本地预览（后端 + 前端 4176）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-dev.ps1 -Preview
```

预览也代理 `/api` 到配置的后端。单独打开 `dist/index.html` 不提供 API 代理，不是完整运行方式。
已经登记运行的同类服务需先停止，再切换模式。

可单独运行启停集成验证：

```powershell
python -B scripts/test_dev_lifecycle.py
```

它会实际启动本地进程并在结束后停止，只访问临时数据库；不调用真实模型。
`CAMPUS_RUNTIME_DIR` 用于将该演练的进程记录、缓存与日志隔离到临时目录。

本轮验证环境：Windows PowerShell 5.1、Python 3.12.3、Node 24.14.0、Vite 6.4.2；
后端已安装 FastAPI 0.136.1、Uvicorn 0.46.0、Pydantic 2.10.6、HTTPX 0.28.1。
这是本机验证记录，不是新的依赖版本限制；本轮没有升级依赖。

## 修改原则

- 脚本应保持 Windows PowerShell 友好。
- 默认端口和 README 总览保持一致：后端 `8766`，前端 `5176`。
- 新增脚本时说明用途、是否会写文件、是否会停止进程。
