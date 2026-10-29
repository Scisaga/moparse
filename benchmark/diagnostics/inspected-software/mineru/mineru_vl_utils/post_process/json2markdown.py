import re

from loguru import logger


def json2md(json_data: dict) -> str:
    content_list = []
    last_text_contd_idx = -1
    for idx, bbox_info in enumerate(json_data):
        try:
            ctype = bbox_info.get("type", "text")
            content = bbox_info["content"]
            if content:
                if bbox_info.get("merge_prev", False) and last_text_contd_idx >= 0:
                    if re.search(r"[\u4e00-\u9fff\u3400-\u4dbf]", content) is not None:
                        # 中文合并的时候不需要加空格，英文需要加一个空格
                        pass
                    else:
                        content = " " + content
                    content_list[last_text_contd_idx] += content
                else:
                    content_list.append(content)
                    if ctype == "text":
                        last_text_contd_idx = len(content_list) - 1
        except Exception as e:
            logger.warning("Failed to process bbox {}: {}; bbox_info: {}", idx, e, bbox_info)
            continue
    md_result = "\n\n".join(content_list)
    return md_result
