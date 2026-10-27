# Plugins · 插件

Bundled Anima plugins. Each folder is one plugin: a `plugin.toml` manifest and a Python entry file
that builds an `anima.plugin.Plugin`. Turn one on for a persona in the console (扩展), or in her
`bot.toml`: `plugins = ["hitokoto"]`. Plugins installed from the market go to `data/plugins/`.

See [docs/plugins.md](../docs/plugins.md) for the API, hooks, and how AstrBot plugins and MCP
servers fit in.
