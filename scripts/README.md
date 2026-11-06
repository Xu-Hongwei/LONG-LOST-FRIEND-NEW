# 脚本说明

这里放本地开发和测试脚本。

## 文件

- `start-dev.ps1`：一键启动后端和前端。
- `start-backend.ps1`：启动后端。
- `start-frontend.ps1`：启动前端。
- `stop-dev.ps1`：按端口停止后端和前端开发进程，默认停止 `8766` 和 `5176`。
- `test-backend.ps1`：运行隔离的后端离线测试，支持 `-Python` 指定解释器，并透传测试退出码。
- `check.ps1`：依次运行后端测试、前端类型检查和生产构建；任何阶段失败即返回非零退出码。

## 常用命令

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

运行后端全量测试：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test-backend.ps1
```

运行前端构建：

```powershell
cd frontend
npm run build
```

## 修改原则

- 脚本应保持 Windows PowerShell 友好。
- 默认端口和 README 总览保持一致：后端 `8766`，前端 `5176`。
- 新增脚本时说明用途、是否会写文件、是否会停止进程。
