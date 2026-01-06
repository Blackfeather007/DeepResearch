#!/usr/bin/env python3
"""
批量调用 OpenAI DeepResearch API 对数学猜想进行文献调研

功能：
- 从 conjectures.json 读取猜想（仅使用 content 字段）
- 并发调用 DeepResearch API
- 错误重试机制（最多3次，指数退避）
- 进度追踪
- 结果保存到 JSON 文件
"""

import json
import yaml
import asyncio
from pathlib import Path
from typing import Dict, List, Optional
from tqdm import tqdm
from openai import (
    AsyncOpenAI,
    RateLimitError,
    APIError,
    APIConnectionError,
    APITimeoutError
)


class DeepResearchBatch:
    """DeepResearch API 批量处理类"""
    
    def __init__(self, config_path: str = "config.yaml", prompt_path: Optional[str] = None):
        """初始化配置"""
        self.config = self._load_config(config_path)
        self.api_key = self.config['api_key']
        self.input_file = self.config['input_file']
        self.output_file = self.config['output_file']
        self.max_retries = self.config.get('max_retries', 3)
        self.concurrency = self.config.get('concurrency', 5)
        
        # 如果配置中有自定义 API URL，使用它；否则使用 OpenAI 官方端点
        api_url = self.config.get('api_url')
        base_url = api_url if api_url else None
        
        # 创建异步 OpenAI 客户端
        # 设置较长的超时时间（3600秒=1小时），因为 Deep Research 可能需要很长时间
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=base_url,
            timeout=3600.0
        )
        
        # 加载 prompt 模板：优先使用参数，其次使用配置，最后使用默认值
        if prompt_path is None:
            prompt_path = self.config.get('prompt_path', 'prompts/prompt_algebra.txt')
        self.prompt_template = self._load_prompt_template(prompt_path)
    
    @staticmethod
    def _load_config(config_path: str) -> Dict:
        """加载 YAML 配置文件"""
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    @staticmethod
    def _load_prompt_template(prompt_path: str) -> str:
        """加载 prompt 模板"""
        prompt_file = Path(prompt_path)
        if not prompt_file.exists():
            # 如果 prompt 文件不存在，使用默认模板
            return "{{conjecture_str}}"
        
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read()
    
    def _build_prompt(self, conjecture_content: str) -> str:
        """使用模板构建完整的 prompt"""
        return self.prompt_template.replace("{{conjecture_str}}", conjecture_content)
    
    def _load_conjectures(self) -> List[Dict]:
        """从 JSON 文件加载猜想，仅提取 informal_statement 字段"""
        input_path = Path(self.input_file)
        if not input_path.exists():
            raise FileNotFoundError(f"输入文件不存在: {self.input_file}")
        
        with open(input_path, 'r', encoding='utf-8') as f:
            conjectures = json.load(f)
        
        # 仅保留 informal_statement 字段
        return [{'content': c.get('informal_statement', '')} for c in conjectures if c.get('informal_statement')]
    
    async def _call_deepresearch(
        self, 
        content: str, 
        retry_count: int = 0
    ) -> Optional[Dict]:
        """
        调用 DeepResearch API
        
        Args:
            content: 猜想内容
            retry_count: 当前重试次数
            
        Returns:
            API 响应结果，失败返回 None
        """
        # 使用模板构建完整的 prompt
        full_prompt = self._build_prompt(content)
        
        try:
            # 原始代码：使用 OpenAI SDK 调用 Responses API（已注释）
            # response = await self.client.responses.create(
            #     model="openai/o3-deep-research",
            #     input=full_prompt,
            #     background=True,
            #     tools=[
            #         {"type": "web_search_preview"},
            #         {"type": "code_interpreter", "container": {"type": "auto"}}
            #     ]
            # )
            # return response
            
            # 新代码：使用 OpenRouter 调用 o3-deep-research（通过 Chat Completions API）
            completion = await self.client.chat.completions.create(
                model="openai/o3-deep-research",
                messages=[
                    {
                        "role": "user",
                        "content": full_prompt
                    }
                ],
                # OpenRouter 会自动处理 web_search 工具
                # 如果需要显式指定，可以添加 extra_headers
            )
            
            # 返回完整的 completion 对象
            return completion
            
        except RateLimitError as e:
            # 处理速率限制错误
            if retry_count < self.max_retries:
                # 速率限制时等待 60 秒
                await asyncio.sleep(60)
                return await self._call_deepresearch(content, retry_count + 1)
            else:
                print(f"达到最大重试次数，跳过该请求（速率限制）: {str(e)}")
                return None
        except (APIConnectionError, APITimeoutError) as e:
            # 处理连接错误和超时错误
            if retry_count < self.max_retries:
                # 指数退避：1s, 2s, 4s
                wait_time = 2 ** retry_count
                await asyncio.sleep(wait_time)
                return await self._call_deepresearch(content, retry_count + 1)
            else:
                print(f"连接失败（已重试 {self.max_retries} 次）: {str(e)}")
                return None
        except APIError as e:
            # 处理其他 API 错误
            if retry_count < self.max_retries:
                # 指数退避：1s, 2s, 4s
                wait_time = 2 ** retry_count
                await asyncio.sleep(wait_time)
                return await self._call_deepresearch(content, retry_count + 1)
            else:
                print(f"API 错误（已重试 {self.max_retries} 次）: {str(e)}")
                return None
        except Exception as e:
            # 处理未知错误
            print(f"未知错误: {str(e)}")
            return None
    
    async def _process_conjecture(
        self,
        conjecture: Dict,
        semaphore: asyncio.Semaphore,
        pbar: tqdm
    ) -> Optional[Dict]:
        """
        处理单个猜想
        
        Args:
            conjecture: 猜想字典（包含 content 字段）
            semaphore: 并发控制信号量
            pbar: 进度条
            
        Returns:
            处理结果字典，包含 content 和 research 字段
        """
        async with semaphore:
            content = conjecture.get('content', '')
            if not content:
                pbar.update(1)
                return None
            
            result = await self._call_deepresearch(content)
            pbar.update(1)
            
            if result:
                # 原始代码：提取 Responses API 的结果（已注释）
                # research_text = getattr(result, 'output_text', '') or str(result)
                
                # 新代码：提取 Chat Completions API 的结果（OpenRouter）
                # Chat Completions API 返回的格式：result.choices[0].message.content
                if hasattr(result, 'choices') and len(result.choices) > 0:
                    research_text = result.choices[0].message.content
                else:
                    research_text = str(result)
                
                return {
                    'content': content,
                    'research': research_text
                }
            else:
                return {
                    'content': content,
                    'research': None,
                    'error': 'API 调用失败'
                }
    
    async def process_all(self):
        """处理所有猜想"""
        print("正在加载猜想数据...")
        conjectures = self._load_conjectures()
        print(f"共加载 {len(conjectures)} 个猜想")
        
        # 创建并发控制信号量
        semaphore = asyncio.Semaphore(self.concurrency)
        
        # 创建任务列表
        tasks = []
        with tqdm(total=len(conjectures), desc="处理进度", unit="个") as pbar:
            for conjecture in conjectures:
                task = self._process_conjecture(conjecture, semaphore, pbar)
                tasks.append(task)
            
            # 并发执行所有任务
            results = await asyncio.gather(*tasks)
        
        # 保存结果
        output_path = Path(self.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 过滤掉 None 结果
        valid_results = [r for r in results if r is not None]
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(valid_results, f, ensure_ascii=False, indent=2)
        
        print(f"\n处理完成！")
        print(f"成功处理: {len(valid_results)}/{len(conjectures)}")
        print(f"结果已保存到: {self.output_file}")


async def main():
    """主函数"""
    try:
        processor = DeepResearchBatch()
        await processor.process_all()
    except KeyboardInterrupt:
        print("\n\n用户中断操作")
    except Exception as e:
        print(f"\n错误: {str(e)}")
        raise


if __name__ == "__main__":
    asyncio.run(main())

