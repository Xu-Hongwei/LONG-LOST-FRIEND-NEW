# 脚本说明

这里放本地开发和测试脚本。

## 文件

- `start-dev.ps1`：一键启动后端和前端。
- `start-backend.ps1`：启动后端。
- `start-frontend.ps1`：启动前端。
- `stop-dev.ps1`：按端口停止后端和前端开发进程，默认停止 `8766` 和 `5176`。
- `test-backend.ps1`：运行后端测试。

## 常用命令

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\stop-dev.ps1
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test-backend.ps1
```

```powershell
cd frontend
npm run build
```
