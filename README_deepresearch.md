# DeepResearch API 批量处理工具

这个工具用于批量调用 OpenAI DeepResearch API 对数学猜想进行文献调研。

## 功能特性

- ✅ 从 `conjectures.json` 读取猜想（仅使用 `informal_statement` 字段）
- ✅ 使用 `prompt.txt` 模板构建完整的调研提示
- ✅ 并发处理多个猜想（可配置并发数）
- ✅ 错误重试机制（最多3次，指数退避）
- ✅ 实时进度追踪
- ✅ 结果保存为 JSON 格式

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置

1. 编辑 `config.yaml` 文件，设置以下参数：

```yaml
api_url: "https://api.openai.com/v1/responses"  # DeepResearch API 端点
api_key: "your_openai_api_key_here"              # 替换为您的 API 密钥
input_file: "data/conjectures.json"              # 输入文件路径
output_file: "data/conjecture_deepresearch.json" # 输出文件路径
max_retries: 3                                    # 最大重试次数
concurrency: 5                                    # 并发数
```

## 使用方法

```bash
python scripts/deepresearch_batch.py
```

## 输出格式

结果保存在 `data/conjecture_deepresearch.json`，格式如下：

```json
[
  {
    "content": "猜想内容...",
    "research": "DeepResearch API 返回的研究结果..."
  },
  ...
]
```

## 注意事项

1. **API 密钥**：请确保在 `config.yaml` 中设置了正确的 OpenAI API 密钥
2. **API 限制**：注意 OpenAI API 的速率限制，适当调整 `concurrency` 参数
3. **超时设置**：每个请求的超时时间为 5 分钟，如需调整可修改代码中的 `timeout` 参数
4. **错误处理**：如果某个猜想处理失败，会在结果中标记 `error` 字段，但不会中断整个处理流程

## 文件结构

```
.
├── config.yaml                          # 配置文件
├── prompt.txt                           # Prompt 模板
├── requirements.txt                     # Python 依赖
├── scripts/
│   └── deepresearch_batch.py           # 主脚本
└── data/
    ├── conjectures.json                 # 输入文件
    └── conjecture_deepresearch.json     # 输出文件（生成）
```

