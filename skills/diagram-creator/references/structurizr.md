# Structurizr DSL

创建或编辑 `.dsl` 文件时读取本参考。Structurizr DSL 用于基于 C4 模型维护软件架构，一个模型可生成系统上下文、容器、组件、动态和部署等一致视图。

## 基本结构

```text
workspace "订单平台" "订单平台架构" {
  model {
    customer = person "客户"
    platform = softwareSystem "订单平台" {
      web = container "Web 应用" "提供用户界面" "Web"
      api = container "API 服务" "处理订单" "Python"
      database = container "数据库" "保存订单" "PostgreSQL"
    }

    customer -> web "使用"
    web -> api "调用" "HTTPS/JSON"
    api -> database "读写" "SQL"
  }

  views {
    systemContext platform "SystemContext" {
      include *
      autoLayout lr
    }
    container platform "Containers" {
      include *
      autoLayout lr
    }
  }
}
```

## 建模要求

- `model` 定义架构事实，`views` 只选择和排列模型内容；不要在多个视图中复制同一元素。
- person、software system、container、component 与 deployment node 保持正确抽象层级。
- 标识符和 view key 显式、稳定，避免自动生成 key 导致布局信息丢失。
- 每条关系使用主动、具体的描述，并在重要场景补充技术或协议。
- 只有多个视图需要共享一致架构语义时才使用 Structurizr；单张临时架构图用 Mermaid、D2 或 Draw.io 更简单。

## 视图和布局

- System Context 面向整体边界和外部参与者。
- Container 视图表达可独立运行或部署的应用与数据存储。
- Component 视图只在组件级信息确有维护价值时创建。
- Dynamic 视图表达一个用例中的有序关系，Deployment 视图表达运行环境实例。
- 默认使用 `autoLayout`，方向与主要阅读顺序一致；需要手工布局时使用 Structurizr 本地工具管理，而不是在 DSL 中伪造坐标。

## include 与安全

DSL 支持 `!include`、脚本、插件、图标和远程资源。默认只使用任务范围内的本地可信资源；不要运行未经信任的脚本或插件，也不要自动将工作区推送到远程服务器。

## 完整验证

使用已安装的 Structurizr 工具执行 workspace 校验。传统 CLI 的命令形式为：

```bash
structurizr.sh validate -workspace workspace.dsl
# Windows
structurizr.bat validate -workspace workspace.dsl
```

不同发行版的命令入口可能不同；以本地版本帮助信息为准。
