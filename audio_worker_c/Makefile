# Audio Worker C Implementation
# High-performance, memory-efficient audio processing worker for Redis job queue
# Supports cross-platform builds (Linux, macOS, Alpine) and multiple architectures (x86_64, ARM64)

# Build configuration
CC ?= gcc
PKG_CONFIG ?= pkg-config
INSTALL ?= install
PREFIX ?= /usr/local

# Version information
VERSION = 1.0.0
BUILD_DATE = $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_COMMIT = $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")

# Compiler flags
BASE_CFLAGS = -Wall -Wextra -Wpedantic -std=c99 -D_GNU_SOURCE
OPT_CFLAGS = -O2 -ffast-math -DNDEBUG
DEBUG_CFLAGS = -O0 -g -DDEBUG -fsanitize=address -fsanitize=undefined
SECURITY_CFLAGS = -fstack-protector-strong -D_FORTIFY_SOURCE=2

# Default flags
CFLAGS ?= $(BASE_CFLAGS) $(OPT_CFLAGS) $(SECURITY_CFLAGS)

# Target architecture detection
UNAME_S := $(shell uname -s)
UNAME_M := $(shell uname -m)

# Architecture-specific optimizations (different for GCC vs Clang)
ifeq ($(CC),clang)
    # Clang on macOS
    ifeq ($(UNAME_M),x86_64)
        ARCH_FLAGS = -march=native -mtune=generic
    else ifeq ($(UNAME_M),arm64)
        ARCH_FLAGS = -mcpu=apple-m1 -mtune=generic
    else
        ARCH_FLAGS = -mtune=generic
    endif
else
    # GCC (Linux containers)
    ifeq ($(UNAME_M),x86_64)
        ARCH_FLAGS = -march=x86-64 -mtune=generic
    else ifeq ($(UNAME_M),aarch64)
        ARCH_FLAGS = -march=armv8-a -mtune=generic
    else
        ARCH_FLAGS = -mtune=generic
    endif
endif

# Platform-specific settings
ifeq ($(UNAME_S),Linux)
    PLATFORM_CFLAGS = -D_GNU_SOURCE
    PLATFORM_LDFLAGS = -Wl,-z,relro,-z,now -static-libgcc
else ifeq ($(UNAME_S),Darwin)
    PLATFORM_CFLAGS = -D_DARWIN_C_SOURCE
    PLATFORM_LDFLAGS = 
else
    PLATFORM_CFLAGS = -D_GNU_SOURCE
    PLATFORM_LDFLAGS = 
endif

# Dependency detection (Alpine/Linux focused)
HIREDIS_CFLAGS = $(shell $(PKG_CONFIG) --cflags hiredis 2>/dev/null || echo "")
HIREDIS_LIBS = $(shell $(PKG_CONFIG) --libs hiredis 2>/dev/null || echo "-lhiredis")
JSON_C_CFLAGS = $(shell $(PKG_CONFIG) --cflags json-c 2>/dev/null || echo "")
JSON_C_LIBS = $(shell $(PKG_CONFIG) --libs json-c 2>/dev/null || echo "-ljson-c")

# Final compiler and linker flags
FINAL_CFLAGS = $(CFLAGS) $(ARCH_FLAGS) $(PLATFORM_CFLAGS) -DVERSION=\"$(VERSION)\" \
               -DBUILD_DATE=\"$(BUILD_DATE)\" -DGIT_COMMIT=\"$(GIT_COMMIT)\"
LDFLAGS = -lm $(HIREDIS_LIBS) $(JSON_C_LIBS) $(PLATFORM_LDFLAGS)

# Directories
SRC_DIR = src
INCLUDE_DIR = include
BUILD_DIR = build
OBJ_DIR = $(BUILD_DIR)/obj

# Source files
SOURCES = $(wildcard $(SRC_DIR)/*.c)
COMMON_SOURCES = $(filter-out $(SRC_DIR)/main.c, $(SOURCES))
COMMON_OBJECTS = $(COMMON_SOURCES:$(SRC_DIR)/%.c=$(OBJ_DIR)/%.o)
MAIN_OBJECT = $(OBJ_DIR)/main.o

# Targets
TARGET = $(BUILD_DIR)/audio_worker
TARGET_NAME = audio_worker

# Include paths
INCLUDES = -I$(INCLUDE_DIR) $(HIREDIS_CFLAGS) $(JSON_C_CFLAGS)

# Dependency checking with better macOS support
REQUIRED_LIBS = hiredis json-c

# Check if libraries are available (pkg-config or direct detection)
HIREDIS_AVAILABLE = $(shell $(PKG_CONFIG) --exists hiredis 2>/dev/null && echo 1 || \
                     (test -f /usr/include/hiredis/hiredis.h && echo 1) || \
                     (test -f /opt/homebrew/include/hiredis/hiredis.h && echo 1) || \
                     echo 0)
JSON_C_AVAILABLE = $(shell $(PKG_CONFIG) --exists json-c 2>/dev/null && echo 1 || \
                    (test -f /usr/include/json-c/json.h && echo 1) || \
                    (test -f /opt/homebrew/include/json-c/json.h && echo 1) || \
                    echo 0)

# Build list of missing libraries
MISSING_LIBS = $(if $(filter 0,$(HIREDIS_AVAILABLE)),hiredis) $(if $(filter 0,$(JSON_C_AVAILABLE)),json-c)

# Default target
.DEFAULT_GOAL := all

# Phony targets
.PHONY: all clean debug release install uninstall deps check-deps test \
        deps-ubuntu deps-debian deps-alpine deps-macos info analyze \
        docker-build docker-test

# Main targets
all: check-deps $(TARGET)

release: CFLAGS = $(BASE_CFLAGS) -O3 -ffast-math -DNDEBUG $(SECURITY_CFLAGS) $(ARCH_FLAGS)
release: clean $(TARGET)

debug: CFLAGS = $(BASE_CFLAGS) $(DEBUG_CFLAGS)
debug: clean $(TARGET)

check-deps:
	@echo "🔍 Checking dependencies..."
	@echo "   hiredis: $(if $(filter 1,$(HIREDIS_AVAILABLE)),✅ found,❌ missing)"
	@echo "   json-c:  $(if $(filter 1,$(JSON_C_AVAILABLE)),✅ found,❌ missing)"
ifneq ($(strip $(MISSING_LIBS)),)
	@echo ""
	@echo "❌ Missing required libraries: $(MISSING_LIBS)"
	@echo "Please install missing dependencies:"
	@echo "  Ubuntu/Debian: sudo apt-get install libhiredis-dev libjson-c-dev"
	@echo "  RHEL/CentOS: sudo yum install hiredis-devel json-c-devel"
	@echo "  Alpine: sudo apk add hiredis-dev json-c-dev"
	@echo "  macOS: brew install hiredis json-c"
	@exit 1
else
	@echo "✅ All dependencies found"
endif

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(OBJ_DIR):
	mkdir -p $(OBJ_DIR)

# Object file compilation with dependency tracking
$(OBJ_DIR)/%.o: $(SRC_DIR)/%.c | $(OBJ_DIR)
	@echo "Compiling $<..."
	$(CC) $(FINAL_CFLAGS) $(INCLUDES) -MMD -MP -c $< -o $@

# Main target linking
$(TARGET): $(COMMON_OBJECTS) $(MAIN_OBJECT) | $(BUILD_DIR)
	@echo "Linking $@..."
	$(CC) $(COMMON_OBJECTS) $(MAIN_OBJECT) $(LDFLAGS) -o $@
	@echo "✅ Built $(TARGET_NAME) v$(VERSION) successfully"
	@echo "   Commit: $(GIT_COMMIT)"
	@echo "   Built:  $(BUILD_DATE)"
	@echo "   Size:   $$(du -h $(TARGET) | cut -f1)"

# Include dependency files
-include $(COMMON_OBJECTS:.o=.d)
-include $(MAIN_OBJECT:.o=.d)

# Installation targets
install: $(TARGET)
	@echo "Installing $(TARGET_NAME) to $(PREFIX)/bin..."
	$(INSTALL) -d $(DESTDIR)$(PREFIX)/bin
	$(INSTALL) -m 755 $(TARGET) $(DESTDIR)$(PREFIX)/bin/$(TARGET_NAME)
	@echo "✅ Installed $(TARGET_NAME) to $(DESTDIR)$(PREFIX)/bin"

uninstall:
	@echo "Uninstalling $(TARGET_NAME) from $(PREFIX)/bin..."
	rm -f $(DESTDIR)$(PREFIX)/bin/$(TARGET_NAME)
	@echo "✅ Uninstalled $(TARGET_NAME)"

# Clean targets
clean:
	@echo "Cleaning build directory..."
	rm -rf $(BUILD_DIR)
	@echo "✅ Cleaned build artifacts"

distclean: clean
	@echo "Deep cleaning..."
	rm -f core core.* *.core vgcore.* *.log
	@echo "✅ Deep clean completed"

# Dependency installation for Linux containers
deps-alpine:
	@echo "Installing dependencies for Alpine Linux..."
	apk add --no-cache build-base hiredis-dev json-c-dev pkgconfig
	@echo "✅ Dependencies installed"

deps-ubuntu:
	@echo "Installing dependencies for Ubuntu/Debian..."
	apt-get update && apt-get install -y build-essential libhiredis-dev libjson-c-dev pkg-config
	@echo "✅ Dependencies installed"

# Default dependency installer (Alpine-focused for containers)
deps: deps-alpine

# Testing targets
test: $(TARGET)
	@echo "🧪 Running functionality tests..."
	@echo "Testing help output:"
	@$(TARGET) --help
	@echo "Testing version output:"
	@$(TARGET) --version
	@echo "✅ Basic tests completed"

# Build information
info:
	@echo "📋 Build Information"
	@echo "==================="
	@echo "Version:     $(VERSION)"
	@echo "Git Commit:  $(GIT_COMMIT)"
	@echo "Build Date:  $(BUILD_DATE)"
	@echo "Platform:    $(UNAME_S) $(UNAME_M)"
	@echo "Compiler:    $(CC)"
	@echo "C Flags:     $(FINAL_CFLAGS)"
	@echo "LD Flags:    $(LDFLAGS)"
	@echo "Target:      $(TARGET)"
	@echo "Prefix:      $(PREFIX)"
	@echo "Sources:     $(words $(SOURCES)) files"

# Static analysis
analyze:
	@echo "🔍 Running static analysis..."
	@if command -v cppcheck >/dev/null 2>&1; then \
		echo "Running cppcheck..."; \
		cppcheck --enable=all --std=c99 --suppress=missingIncludeSystem $(SRC_DIR) $(INCLUDE_DIR); \
	else \
		echo "⚠️  cppcheck not available"; \
	fi
	@if command -v clang-tidy >/dev/null 2>&1; then \
		echo "Running clang-tidy..."; \
		clang-tidy $(SOURCES) -- $(INCLUDES) $(FINAL_CFLAGS); \
	else \
		echo "⚠️  clang-tidy not available"; \
	fi
	@echo "✅ Static analysis completed"

# Docker build targets (Linux AMD64 focused)
docker-build:
	@echo "🐳 Building Docker image for Linux AMD64..."
	docker build --platform linux/amd64 -t $(TARGET_NAME):$(VERSION) .
	@echo "✅ Docker image built"

docker-test:
	@echo "🐳 Testing Docker image..."
	docker run --rm $(TARGET_NAME):$(VERSION) --version
	@echo "✅ Docker test completed"

# Help target
help:
	@echo "📖 Available Make Targets"
	@echo "========================"
	@echo "Build targets:"
	@echo "  all          - Build the audio worker (default)"
	@echo "  release      - Build optimized release version"
	@echo "  debug        - Build debug version with sanitizers"
	@echo "  clean        - Remove build artifacts"
	@echo "  distclean    - Deep clean including core files"
	@echo ""
	@echo "Installation:"
	@echo "  install      - Install to $(PREFIX)/bin"
	@echo "  uninstall    - Remove from $(PREFIX)/bin"
	@echo ""
	@echo "Dependencies:"
	@echo "  deps         - Install platform-specific dependencies"
	@echo "  deps-ubuntu  - Install Ubuntu/Debian dependencies"
	@echo "  deps-alpine  - Install Alpine Linux dependencies"
	@echo "  deps-macos   - Install macOS dependencies"
	@echo "  check-deps   - Verify required libraries are installed"
	@echo ""
	@echo "Testing & Analysis:"
	@echo "  test         - Run basic functionality tests"
	@echo "  analyze      - Run static analysis tools"
	@echo ""
	@echo "Information:"
	@echo "  info         - Show build configuration"
	@echo "  help         - Show this help"
	@echo ""
	@echo "Docker:"
	@echo "  docker-build - Build multi-arch Docker image"
	@echo "  docker-test  - Test Docker image"