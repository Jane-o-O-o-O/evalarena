#!/bin/bash
export PATH=/usr/local/bin:/usr/bin:/bin:$PATH
export HOME=/root
cd /tmp/dev/evalarena
git pull origin main 2>/dev/null

claude -p --allowedTools "Bash,Read,Write,Edit,MultiEdit" "你是一个资深Python工程师，正在开发Jane-o-O-o-O/evalarena（LLM 对战竞技场：盲评对比、ELO 评分、排行榜）。工作目录: /tmp/dev/evalarena

核心原则：每次开发必须有意义，不做凑时间代码，不重复造轮子YAGNI。

流程：1)规划5分钟，看git log和src/，制定3-5个TODO 2)TDD开发：写测试→写实现→重构→commit(中文) 3)收尾：全量测试、git push、总结

重点方向(按优先级)：按README中的Roadmap选择当前最有价值的方向开发。代码要求：类型注解、docstring、错误处理。"

COMMIT_COUNT=$(git log --oneline --since="1 hour ago" 2>/dev/null | wc -l)
/tmp/dev/evalarena/notify.sh "evalarena" "本次开发完成" "新增 ${COMMIT_COUNT} 个commit"

git push origin main 2>/dev/null
