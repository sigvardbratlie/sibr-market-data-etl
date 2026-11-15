# sibr-market – bygg, push og deploy til k8s (Talos på Raspberry Pi)
#
#   make build-push                 # alle images, arm64, tag = latest (normalt gjør CI dette)
#   make build-push MODULES=scraping
#   make secrets                    # .env -> deploy/helm/sibr-market/values.secrets.yaml (gitignored)
#   make deploy                     # helm upgrade --install med secrets
#   make run-now                    # trigger pipelinen umiddelbart
#   make logs                       # følg siste jobb

REGISTRY  ?= ghcr.io/sigvardbratlie
PREFIX    ?= sibr-
MODULES   ?= scraping modeling api cadastral
PLATFORMS ?= linux/arm64
NS        ?= sibr-market
RELEASE   ?= sibr-market
CHART     := deploy/helm/sibr-market
SECRETS   := $(CHART)/values.secrets.yaml
# latest + pullPolicy Always: hver kjøring henter nyeste image fra main.
# CI bygger kun moduler som er endret, så sha-<HEAD> finnes ikke alltid for alle moduler.
# Pin ved behov: make deploy TAG=sha-abc1234
TAG       ?= latest

.PHONY: build-push build-local login secrets namespace deploy template diff run-now run-step logs status uninstall

login: ## docker login ghcr.io (krever GHCR_TOKEN med write:packages)
	@echo "$$GHCR_TOKEN" | docker login ghcr.io -u sigvardbratlie --password-stdin

build-push: ## Bygg og push multi-arch images til GHCR
	@for m in $(MODULES); do \
	  echo "▶ $$m"; \
	  docker buildx build --platform $(PLATFORMS) \
	    -t $(REGISTRY)/$(PREFIX)$$m:$(TAG) -t $(REGISTRY)/$(PREFIX)$$m:latest \
	    --push ./$$m || exit 1; \
	done

build-local: ## Bygg images lokalt (for docker compose)
	docker compose --profile job build

secrets: ## Generer values.secrets.yaml fra */.env
	python3 deploy/scripts/env-to-values.py

namespace: ## Namespace med Pod Security restricted (én gang)
	kubectl create namespace $(NS) --dry-run=client -o yaml | kubectl apply -f -
	kubectl label namespace $(NS) --overwrite pod-security.kubernetes.io/enforce=restricted

template: ## Render chart lokalt
	helm template $(RELEASE) $(CHART) -n $(NS) --set image.tag=$(TAG)

deploy: namespace ## Installer/oppgrader chart i clusteret
	helm upgrade --install $(RELEASE) $(CHART) -n $(NS) -f $(SECRETS) --set image.tag=$(TAG)

run-now: ## Trigger pipelinen nå
	kubectl -n $(NS) create job --from=cronjob/$(RELEASE)-pipeline pipeline-manual-$$(date +%s)

run-step: ## Kjør ett steg: make run-step STEP=api
	kubectl -n $(NS) create job --from=cronjob/$(RELEASE)-$(STEP) $(STEP)-manual-$$(date +%s)

logs: ## Følg logger for nyeste jobb
	kubectl -n $(NS) logs -f --all-containers --max-log-requests 10 \
	  $$(kubectl -n $(NS) get pods --sort-by=.metadata.creationTimestamp -o name | tail -1)

status:
	kubectl -n $(NS) get cronjobs,jobs,pods

uninstall:
	helm uninstall $(RELEASE) -n $(NS)
