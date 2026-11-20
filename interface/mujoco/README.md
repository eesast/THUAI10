# MuJoCo 选手网页

网页由 `logic/mujoco` 的服务在 `/static/` 提供，不需要额外 Node.js 服务。页面包含策略上传、练习、正式比赛、结果回放、赛事总榜及管理员维护。

开发格式检查：

```powershell
npm ci --ignore-scripts --prefix interface/mujoco
npm run format:check --prefix interface/mujoco
```

使用 UTF-8、4 空格、Prettier 3.10.1。部署方式见 [后端说明](../../logic/mujoco/README.md)。本目录是原型网页，与规划中的 Unity 客户端并存。
