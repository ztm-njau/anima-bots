# 安全策略 · Security policy

## 报告漏洞 · Reporting a vulnerability

请不要在公开 issue 里报告安全问题。到仓库的 **Security → Report a vulnerability** 提交私密报告，
写清楚影响、复现步骤和你使用的版本（提交号）。我们会尽快确认，修复后在发布说明里致谢（如果你愿意）。

Please don't open a public issue. Use **Security → Report a vulnerability** on GitHub with the
impact, steps to reproduce and the commit you tested. We'll acknowledge it promptly and credit you
in the release notes if you'd like.

## 支持的版本 · Supported versions

只有 `main` 分支的最新提交会收到安全修复。Only the latest `main` receives fixes.

## 设计上的安全边界 · Security model

- 网页和 API 只监听 `127.0.0.1`，并拒绝来自其他域名或主机名的请求和 WebSocket（防 CSRF、DNS 重绑定）。
  The web server binds to `127.0.0.1` and refuses requests and sockets from other origins or hosts.
- 浏览器永远拿不到完整的 API key（只显示 `sk-…abcd`）。Keys never reach the browser.
- 密钥只保存在 `.env`、`data/providers.json`（权限 600）和 `data/<bot>/secrets/`，都不进 git。
  Secrets live only in gitignored files; `data/providers.json` is mode 600.
- OpenAI 兼容接口 `/v1` 默认只接受本机请求；设置 `ANIMA_API_KEY` 后才允许其他机器或容器访问。
  The `/v1` endpoint is local-only unless `ANIMA_API_KEY` is set.
- MCP 插件会在你的电脑上运行第三方程序，只添加你信任的服务器。
  MCP plugins run third-party programs on your machine; add only servers you trust.

特别欢迎这些方面的报告：本地接口的越权访问、密钥泄露、提示注入导致她泄露设定或越界、
平台适配器把消息发到不该发的地方。

Reports we especially want: unauthorised access to the local API, key leaks, prompt injection that
makes her leak her instructions or cross her boundaries, and adapters sending messages where they
shouldn't.
