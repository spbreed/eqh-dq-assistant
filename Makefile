# EQH DQ Assistant pilot. All targets source scripts/env.sh (region, venv, PYTHONPATH). Deploys are 🛑 checkpoints.
SHELL := /bin/bash
ENV := source scripts/env.sh &&
CDK := cd infra && cdk
TAG = $(shell cut -d= -f2 build/image_tag 2>/dev/null)
CTX = -c image_tag=$(TAG) -c schedule_state=$(or $(SCHEDULE),DISABLED)
N ?= 22
INJECT ?=

.PHONY: help venv bootstrap image deploy-all deploy seed simulate simulate-day redetect enrich eval eval-local \
        test test-aws verify security-check pause resume destroy smoke

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

venv:            ## create .venv with dev dependencies
	uv venv -q -p 3.12 .venv && . .venv/bin/activate && uv pip install -q -r requirements.txt aws-cdk-lib constructs \
	  numpy pandas pyarrow faker pytest

bootstrap:       ## verify identity matches config, cdk bootstrap, LLM smoke (Phase 0)
	$(ENV) scripts/verify_phase0.sh && $(CDK) bootstrap

image:           ## build the container image in CodeBuild (EqhDqImage) and record its tag
	$(ENV) $(CDK) deploy EqhDqImage --require-approval never && cd .. && echo "TAG=$$(scripts/build_image.sh)" > build/image_tag

deploy-all: image  ## 🛑 deploy every stack
	$(ENV) $(CDK) deploy --all $(CTX) --require-approval never

deploy:          ## 🛑 deploy one stack: make deploy STACK=EqhDqAssistant
	$(ENV) $(CDK) deploy $(STACK) $(CTX) --require-approval never

seed:            ## migrations + generate data + day-0 load and sync
	$(ENV) python -m metadata_store.migrate && python -m datagen.simulate build && python -m datagen.simulate seed

simulate:        ## replay simulated days 1..21, then re-run detection and enrichment
	$(ENV) python -m datagen.simulate days 1 21 && python -m jobs.daily_sync.sync --redetect && $(MAKE) enrich

simulate-day:    ## live demo day: make simulate-day N=22 INJECT=D07
	$(ENV) python -m datagen.simulate day $(N) $(if $(INJECT),--inject $(INJECT))

redetect:        ## replay issue detection over stored metrics
	$(ENV) python -m jobs.daily_sync.sync --redetect

enrich:          ## AI documentation drafts (runs in Fargate: models are reached via bedrock-mantle)
	$(ENV) scripts/run_task.sh enrich

smoke:           ## LLM smoke test in Fargate
	$(ENV) scripts/run_task.sh llm_smoke

eval:            ## golden-question eval in Fargate; downloads eval/report.html
	$(ENV) TAIL=30 scripts/run_task.sh eval python -m eval.run_eval --upload && \
	  aws s3 cp s3://eqh-dq-$$(python -c 'from jobs.common import settings;print(settings.get()["account_id"])')-dq-results/eval/latest/report.html eval/report.html

test:            ## offline unit tests
	$(ENV) python -m pytest -q tests

test-aws:        ## unit + integration tests against the deployed pilot (PHI guard on store/logs)
	$(ENV) python -m pytest -q tests --aws

verify:          ## run all phase verification scripts
	$(ENV) for f in scripts/verify_phase*.sh; do echo "== $$f"; $$f || exit 1; done

security-check:  ## security self-check (Phase 7)
	$(ENV) python scripts/security_selfcheck.py

pause:           ## scale down: Aurora min 0 ACU (auto-pause), assistant to 0 tasks, scheduler disabled
	$(ENV) scripts/pause_resume.sh pause

resume:          ## scale back up
	$(ENV) scripts/pause_resume.sh resume

destroy:         ## 🛑 typed confirmation -> empty buckets -> delete snapshots -> cdk destroy --all -> verify
	$(ENV) scripts/destroy.sh
