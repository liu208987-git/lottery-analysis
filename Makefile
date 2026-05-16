# lottery-analysis Makefile
# 用法: make <target>
# Windows 用户: Git Bash 自带 make，或在 PowerShell 中使用对应 python 命令

LOTTERY ?= pls
TOP_K  ?= 30
STRATEGY ?= default

.PHONY: daily daily-review backtest compare review tune clean help

## 每日预测（Hermes 17:30）
daily:
	python run_daily.py --top-k $(TOP_K) --strategy $(STRATEGY)

## 每日复盘（Hermes 22:00）
daily-review:
	python scripts/daily_review.py

## Walk-forward 回测
backtest:
	python scripts/backtest.py --lottery $(LOTTERY) --periods 100 --top-k $(TOP_K)

## 预测 vs 开奖对比
compare:
	python scripts/compare_result.py --lottery $(LOTTERY)

## 复盘表现摘要
review:
	python scripts/review_summary.py

## 权重自动调优（需 review_history >= 15 期）
tune:
	python scripts/tune_weights.py --lottery $(LOTTERY) --trials 30 --periods 50

## 可视化（HTML 交互图）
chart:
	python scripts/visualize.py --lottery $(LOTTERY) --chart all --output-format html

## 清理输出文件
clean:
	@echo "清理 output/ 下的预测和图表..."
	rm -rf output/predictions/*.json
	rm -rf output/charts/*
	rm -rf output/backtests/*
	rm -rf output/tuning/*
	@echo "完成"

help:
	@echo "用法: make <target> [LOTTERY=pls|d3] [TOP_K=30] [STRATEGY=default|conservative|diversity|all]"
	@echo ""
	@echo "  make daily      每日预测（默认Top-30，默认策略）"
	@echo "  make backtest   Walk-forward 回测"
	@echo "  make compare    预测 vs 开奖对比"
	@echo "  make review     复盘表现摘要"
	@echo "  make tune       权重自动调优"
	@echo "  make chart      生成可视化图表"
	@echo "  make clean      清理输出文件"
	@echo ""
	@echo "示例:"
	@echo "  make daily LOTTERY=pls TOP_K=10 STRATEGY=conservative"
	@echo "  make backtest LOTTERY=d3 TOP_K=30"
