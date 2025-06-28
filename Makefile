# === Variables ===
CONTAINER_NAME = caf-dev-container
IMAGE_NAME = caf-dev-image
WORKSPACE_DIR ?= $(PWD)
ENABLE_COVERAGE ?= 0

# === Container Management ===

build-container:
	@if [ -z "$$(docker images -q $(IMAGE_NAME))" ]; then \
		echo "🚀 Building Docker image: $(IMAGE_NAME)"; \
		docker buildx build -t $(IMAGE_NAME) .; \
	else \
		echo "✅ Docker image $(IMAGE_NAME) already exists."; \
	fi

run: build-container
	@echo "🏃 Running container: $(CONTAINER_NAME)"
	@if [ $$(docker ps -a -q -f name=$(CONTAINER_NAME)) ]; then \
		if [ $$(docker ps -q -f name=$(CONTAINER_NAME)) ]; then \
			echo "🎉 Container already running!"; \
		else \
			echo "🔄 Starting existing stopped container..."; \
			docker start $(CONTAINER_NAME); \
		fi \
	else \
		echo "✨ Creating and running new container..."; \
		docker run --detach -it --name $(CONTAINER_NAME) \
			-v $(WORKSPACE_DIR):/workspace $(IMAGE_NAME); \
	fi

attach: run
	@echo "🔗 Attaching to container: $(CONTAINER_NAME)"
	docker attach $(CONTAINER_NAME)

stop:
	@echo "🛑 Stopping container: $(CONTAINER_NAME)"
	@docker stop $(CONTAINER_NAME) 2>/dev/null || true

# === Build & Install ===

deploy_libcaf:
	@echo "📦 Deploying libcaf library..."
	cd libcaf && CMAKE_ARGS="-DENABLE_COVERAGE=$(ENABLE_COVERAGE)" pip install --no-build-isolation -v -e . \
	&& cd .. && pybind11-stubgen _libcaf -o libcaf

deploy_caf:
	@echo "📦 Deploying caf CLI..."
	pip install -e caf

deploy: deploy_libcaf deploy_caf
	@echo "✅ Deployment complete!"

# === Testing ===

test:
	@echo "🧪 Running tests..."
ifeq ($(ENABLE_COVERAGE), 1)
		@echo "📊 Generating coverage report..."
		mkdir -p coverage
		lcov --zerocounters --directory libcaf
		lcov --ignore-errors mismatch --capture --initial --directory libcaf --output-file coverage/base.info
		-COVERAGE_FILE=coverage/.coverage python -m pytest --cov=libcaf --cov=caf --cov-report=lcov:coverage/python_coverage.info tests
		lcov --ignore-errors mismatch --directory libcaf --capture --output-file coverage/run.info
		lcov --add-tracefile coverage/base.info --add-tracefile coverage/run.info --add-tracefile coverage/python_coverage.info --output-file coverage/combined_coverage.info
		lcov --remove coverage/combined_coverage.info '/usr/*' 'pybind' --output-file coverage/combined_coverage.info
		lcov --ignore-errors mismatch --list coverage/combined_coverage.info
		@echo "📂 Generating combined HTML report..."
		genhtml coverage/combined_coverage.info --output-directory coverage
else
		pytest tests
endif

# === Utility ===

clean_coverage:
	rm -f libcaf/*.gcda
	rm -rf tests/.coverage
	rm -r coverage

clean: clean_coverage
	rm -rf libcaf/libcaf.egg-info libcaf/*.so libcaf/build
	rm -rf caf/caf.egg-info

help:
	@echo "🌟 Available targets:"
	@echo "  build-container         - Build the Docker image"
	@echo "  run                     - Run the Docker container"
	@echo "  attach                  - Attach to the running Docker container"
	@echo "  stop                    - Stop the Docker container"
	@echo ""
	@echo "  develop                 - Compile with coverage flags if enabled"
	@echo "  deploy_libcaf           - Install libcaf in editable mode"
	@echo "  deploy_caf              - Install caf in editable mode"
	@echo "  deploy                  - Install both components"
	@echo ""
	@echo "  test                    - Run all tests (Python + C++ coverage if enabled)"
	@echo ""
	@echo "  clean_coverage          - Remove coverage files"
	@echo "  clean                   - Remove build artifacts"
	@echo ""
	@echo "Options:"
	@echo "  ENABLE_COVERAGE=1          - Enable C++ coverage (default: 0)"
	@echo "  Example: make test ENABLE_COVERAGE=1"

.PHONY: \
	build-container run attach stop \
	develop deploy deploy_libcaf deploy_caf \
	test \
	clean_coverage clean help
