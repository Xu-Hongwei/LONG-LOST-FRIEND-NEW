# 脚本说明

这里放本地开发和测试脚本。

## 文件

- `start-dev.ps1`：一键启动后端和前端。
- `start-backend.ps1`：启动后端。
- `start-frontend.ps1`：启动前端。
- `stop-dev.ps1`：按端口停止后端和前端开发进程，默认停止 `8766` 和 `5176`。
- `test-backend.ps1`：运行后端测试。

## 常用命令

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
