.PHONY: install
install: ## Install the virtual environment and install the pre-commit hooks
	@echo "🚀 Creating virtual environment using uv"
	@uv sync
	@uv run pre-commit install


.PHONY: check
check: ## Run code quality tools.
	@echo "🚀 Checking lock file consistency with 'pyproject.toml'"
	@uv lock --locked
	@echo "🚀 Linting code: Running pre-commit"
	@uv run pre-commit run -a
	@echo "🚀 Static type checking: Running mypy"
	@uv run mypy
	@echo "🚀 Checking for obsolete dependencies: Running deptry"
	@uv run deptry src

.PHONY: test
test: ## Test the code with pytest
	@echo "🚀 Testing code: Running pytest"
	@uv run python -m pytest --cov --cov-config=pyproject.toml --cov-report=xml

.PHONY: schema-test
schema-test: ## Run schema validation tests
	@echo "🚀 Running CLI validation commands"
	@uv run python -m katachi validate "tests/schema_tests/test_sanity/schema.yaml" "tests/schema_tests/test_sanity/dataset"
	@uv run python -m katachi validate "tests/schema_tests/test_depth_1/schema.yaml" "tests/schema_tests/test_depth_1/dataset"
	@uv run python -m katachi validate "tests/schema_tests/test_paired_files/schema.yaml" "tests/schema_tests/test_paired_files/data"
	@uv run python -m katachi validate "tests/schema_tests/test_depth_2/schema.yaml" "tests/schema_tests/test_depth_2/dataset_root"
	@uv run python -m katachi validate "tests/schema_tests/test_ambiguous_dirs/schema.yaml" "tests/schema_tests/test_ambiguous_dirs/root"

.PHONY: bench
bench: ## Run the benchmark (100k files)
	@uv run python benchmarks/bench.py --dirs 200 --files 250

.PHONY: json-schema
json-schema: ## Regenerate katachi.schema.json
	@uv run katachi json-schema > katachi.schema.json

.PHONY: build
build: clean-build ## Build wheel file
	@echo "🚀 Creating wheel file"
	@uvx --from build pyproject-build --installer uv

.PHONY: clean-build
clean-build: ## Clean build artifacts
	@echo "🚀 Removing build artifacts"
	@uv run python -c "import shutil; import os; shutil.rmtree('dist') if os.path.exists('dist') else None"

.PHONY: publish
publish: ## Publish a release to PyPI.
	@echo "🚀 Publishing."
	@uvx twine upload --repository-url https://upload.pypi.org/legacy/ dist/*

.PHONY: build-and-publish
build-and-publish: build publish ## Build and publish.

.PHONY: docs-test
docs-test: ## Test if documentation can be built without warnings or errors
	@uv run mkdocs build -s

.PHONY: docs
docs: ## Build and serve the documentation
	@uv run mkdocs serve

.PHONY: help
help:
	@uv run python -c "import re; \
	[[print(f'\033[36m{m[0]:<20}\033[0m {m[1]}') for m in re.findall(r'^([a-zA-Z_-]+):.*?## (.*)$$', open(makefile).read(), re.M)] for makefile in ('$(MAKEFILE_LIST)').strip().split()]"

.DEFAULT_GOAL := help
