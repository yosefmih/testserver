
// this file is generated — do not edit it


/// <reference types="@sveltejs/kit" />

/**
 * This module provides access to environment variables that are injected _statically_ into your bundle at build time and are limited to _private_ access.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Static environment variables are [loaded by Vite](https://vitejs.dev/guide/env-and-mode.html#env-files) from `.env` files and `process.env` at build time and then statically injected into your bundle at build time, enabling optimisations like dead code elimination.
 * 
 * **_Private_ access:**
 * 
 * - This module cannot be imported into client-side code
 * - This module only includes variables that _do not_ begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) _and do_ start with [`config.kit.env.privatePrefix`](https://svelte.dev/docs/kit/configuration#env) (if configured)
 * 
 * For example, given the following build time environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://site.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { ENVIRONMENT, PUBLIC_BASE_URL } from '$env/static/private';
 * 
 * console.log(ENVIRONMENT); // => "production"
 * console.log(PUBLIC_BASE_URL); // => throws error during build
 * ```
 * 
 * The above values will be the same _even if_ different values for `ENVIRONMENT` or `PUBLIC_BASE_URL` are set at runtime, as they are statically replaced in your code with their build time values.
 */
declare module '$env/static/private' {
	export const CLAUDE_TMPDIR: string;
	export const NoDefaultCurrentDirectoryInExePath: string;
	export const CLAUDE_EFFORT: string;
	export const CLAUDE_CODE_ENTRYPOINT: string;
	export const VSCODE_GIT_IPC_AUTH_TOKEN: string;
	export const TERM_PROGRAM: string;
	export const NODE: string;
	export const FNM_LOGLEVEL: string;
	export const INIT_CWD: string;
	export const CLAUDE_CODE_BRIDGE_SESSION_ID: string;
	export const SHELL: string;
	export const TERM: string;
	export const DOCKER_HTTPS_PROXY: string;
	export const FNM_NODE_DIST_MIRROR: string;
	export const CLAUDE_CODE_CHILD_SESSION: string;
	export const TMPDIR: string;
	export const HOMEBREW_REPOSITORY: string;
	export const npm_config_global_prefix: string;
	export const DOCKER_HOST: string;
	export const CURSOR_CLI: string;
	export const TERM_PROGRAM_VERSION: string;
	export const FPATH: string;
	export const GVM_ROOT: string;
	export const GIT_CONFIG_PARAMETERS: string;
	export const ZDOTDIR: string;
	export const MallocNanoZone: string;
	export const COLOR: string;
	export const TERM_SESSION_ID: string;
	export const npm_config_noproxy: string;
	export const npm_config_local_prefix: string;
	export const ENABLE_IDE_INTEGRATION: string;
	export const ZSH: string;
	export const AWS_PAGER: string;
	export const NO_PROXY: string;
	export const GIT_EDITOR: string;
	export const AI_AGENT: string;
	export const FNM_COREPACK_ENABLED: string;
	export const CLOUDSDK_PROXY_ADDRESS: string;
	export const http_proxy: string;
	export const USER: string;
	export const CLOUDSDK_PROXY_PORT: string;
	export const DOCKER_HTTP_PROXY: string;
	export const LD_LIBRARY_PATH: string;
	export const LS_COLORS: string;
	export const CLOUDSDK_PROXY_USERNAME: string;
	export const COMMAND_MODE: string;
	export const npm_config_globalconfig: string;
	export const CLAUDE_CODE_SSE_PORT: string;
	export const SSH_AUTH_SOCK: string;
	export const ftp_proxy: string;
	export const FTP_PROXY: string;
	export const VSCODE_PROFILE_INITIALIZED: string;
	export const __CF_USER_TEXT_ENCODING: string;
	export const npm_execpath: string;
	export const CLOUDSDK_PROXY_PASSWORD: string;
	export const VIRTUAL_ENV: string;
	export const PAGER: string;
	export const PYDEVD_DISABLE_FILE_VALIDATION: string;
	export const LSCOLORS: string;
	export const FNM_VERSION_FILE_STRATEGY: string;
	export const all_proxy: string;
	export const ALL_PROXY: string;
	export const FNM_ARCH: string;
	export const GRPC_PROXY: string;
	export const PATH: string;
	export const RSYNC_PROXY: string;
	export const npm_package_json: string;
	export const _: string;
	export const LaunchInstanceID: string;
	export const npm_config_userconfig: string;
	export const npm_config_init_module: string;
	export const USER_ZDOTDIR: string;
	export const __CFBundleIdentifier: string;
	export const npm_command: string;
	export const GVM_VERSION: string;
	export const PWD: string;
	export const npm_lifecycle_event: string;
	export const EDITOR: string;
	export const npm_package_name: string;
	export const LANG: string;
	export const gvm_pkgset_name: string;
	export const BUNDLED_DEBUGPY_PATH: string;
	export const CURSOR_CLI_MODE: string;
	export const npm_config_npm_version: string;
	export const VSCODE_GIT_ASKPASS_EXTRA_ARGS: string;
	export const XPC_FLAGS: string;
	export const FNM_MULTISHELL_PATH: string;
	export const npm_config_node_gyp: string;
	export const JAVA_TOOL_OPTIONS: string;
	export const https_proxy: string;
	export const HTTPS_PROXY: string;
	export const npm_package_version: string;
	export const XPC_SERVICE_NAME: string;
	export const SANDBOX_RUNTIME: string;
	export const VSCODE_INJECTION: string;
	export const VSCODE_DEBUGPY_ADAPTER_ENDPOINTS: string;
	export const HOME: string;
	export const SHLVL: string;
	export const GOROOT: string;
	export const VSCODE_GIT_ASKPASS_MAIN: string;
	export const CLOUDSDK_PROXY_TYPE: string;
	export const TMPPREFIX: string;
	export const CLAUDE_CODE_EXECPATH: string;
	export const no_proxy: string;
	export const HOMEBREW_PREFIX: string;
	export const GIT_SSH_COMMAND: string;
	export const HTTP_PROXY: string;
	export const gvm_go_name: string;
	export const FNM_DIR: string;
	export const npm_config_cache: string;
	export const LESS: string;
	export const LOGNAME: string;
	export const npm_lifecycle_script: string;
	export const GVM_OVERLAY_PREFIX: string;
	export const CLAUDE_CODE_TMPDIR: string;
	export const VSCODE_GIT_IPC_HANDLE: string;
	export const COREPACK_ENABLE_AUTO_PIN: string;
	export const GOPATH: string;
	export const BUN_INSTALL: string;
	export const GITHUB_TOKEN: string;
	export const PKG_CONFIG_PATH: string;
	export const npm_config_user_agent: string;
	export const FNM_RESOLVE_ENGINES: string;
	export const CLAUDE_CODE_SESSION_ID: string;
	export const VSCODE_GIT_ASKPASS_NODE: string;
	export const GIT_ASKPASS: string;
	export const HOMEBREW_CELLAR: string;
	export const INFOPATH: string;
	export const grpc_proxy: string;
	export const CLAUDECODE: string;
	export const SECURITYSESSIONID: string;
	export const VIRTUAL_ENV_PROMPT: string;
	export const npm_node_execpath: string;
	export const npm_config_prefix: string;
	export const COLORTERM: string;
	export const GVM_PATH_BACKUP: string;
	export const NODE_ENV: string;
}

/**
 * This module provides access to environment variables that are injected _statically_ into your bundle at build time and are _publicly_ accessible.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Static environment variables are [loaded by Vite](https://vitejs.dev/guide/env-and-mode.html#env-files) from `.env` files and `process.env` at build time and then statically injected into your bundle at build time, enabling optimisations like dead code elimination.
 * 
 * **_Public_ access:**
 * 
 * - This module _can_ be imported into client-side code
 * - **Only** variables that begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) (which defaults to `PUBLIC_`) are included
 * 
 * For example, given the following build time environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://site.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { ENVIRONMENT, PUBLIC_BASE_URL } from '$env/static/public';
 * 
 * console.log(ENVIRONMENT); // => throws error during build
 * console.log(PUBLIC_BASE_URL); // => "http://site.com"
 * ```
 * 
 * The above values will be the same _even if_ different values for `ENVIRONMENT` or `PUBLIC_BASE_URL` are set at runtime, as they are statically replaced in your code with their build time values.
 */
declare module '$env/static/public' {
	
}

/**
 * This module provides access to environment variables set _dynamically_ at runtime and that are limited to _private_ access.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Dynamic environment variables are defined by the platform you're running on. For example if you're using [`adapter-node`](https://github.com/sveltejs/kit/tree/main/packages/adapter-node) (or running [`vite preview`](https://svelte.dev/docs/kit/cli)), this is equivalent to `process.env`.
 * 
 * **_Private_ access:**
 * 
 * - This module cannot be imported into client-side code
 * - This module includes variables that _do not_ begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) _and do_ start with [`config.kit.env.privatePrefix`](https://svelte.dev/docs/kit/configuration#env) (if configured)
 * 
 * > [!NOTE] In `dev`, `$env/dynamic` includes environment variables from `.env`. In `prod`, this behavior will depend on your adapter.
 * 
 * > [!NOTE] To get correct types, environment variables referenced in your code should be declared (for example in an `.env` file), even if they don't have a value until the app is deployed:
 * >
 * > ```env
 * > MY_FEATURE_FLAG=
 * > ```
 * >
 * > You can override `.env` values from the command line like so:
 * >
 * > ```sh
 * > MY_FEATURE_FLAG="enabled" npm run dev
 * > ```
 * 
 * For example, given the following runtime environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://site.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { env } from '$env/dynamic/private';
 * 
 * console.log(env.ENVIRONMENT); // => "production"
 * console.log(env.PUBLIC_BASE_URL); // => undefined
 * ```
 */
declare module '$env/dynamic/private' {
	export const env: {
		CLAUDE_TMPDIR: string;
		NoDefaultCurrentDirectoryInExePath: string;
		CLAUDE_EFFORT: string;
		CLAUDE_CODE_ENTRYPOINT: string;
		VSCODE_GIT_IPC_AUTH_TOKEN: string;
		TERM_PROGRAM: string;
		NODE: string;
		FNM_LOGLEVEL: string;
		INIT_CWD: string;
		CLAUDE_CODE_BRIDGE_SESSION_ID: string;
		SHELL: string;
		TERM: string;
		DOCKER_HTTPS_PROXY: string;
		FNM_NODE_DIST_MIRROR: string;
		CLAUDE_CODE_CHILD_SESSION: string;
		TMPDIR: string;
		HOMEBREW_REPOSITORY: string;
		npm_config_global_prefix: string;
		DOCKER_HOST: string;
		CURSOR_CLI: string;
		TERM_PROGRAM_VERSION: string;
		FPATH: string;
		GVM_ROOT: string;
		GIT_CONFIG_PARAMETERS: string;
		ZDOTDIR: string;
		MallocNanoZone: string;
		COLOR: string;
		TERM_SESSION_ID: string;
		npm_config_noproxy: string;
		npm_config_local_prefix: string;
		ENABLE_IDE_INTEGRATION: string;
		ZSH: string;
		AWS_PAGER: string;
		NO_PROXY: string;
		GIT_EDITOR: string;
		AI_AGENT: string;
		FNM_COREPACK_ENABLED: string;
		CLOUDSDK_PROXY_ADDRESS: string;
		http_proxy: string;
		USER: string;
		CLOUDSDK_PROXY_PORT: string;
		DOCKER_HTTP_PROXY: string;
		LD_LIBRARY_PATH: string;
		LS_COLORS: string;
		CLOUDSDK_PROXY_USERNAME: string;
		COMMAND_MODE: string;
		npm_config_globalconfig: string;
		CLAUDE_CODE_SSE_PORT: string;
		SSH_AUTH_SOCK: string;
		ftp_proxy: string;
		FTP_PROXY: string;
		VSCODE_PROFILE_INITIALIZED: string;
		__CF_USER_TEXT_ENCODING: string;
		npm_execpath: string;
		CLOUDSDK_PROXY_PASSWORD: string;
		VIRTUAL_ENV: string;
		PAGER: string;
		PYDEVD_DISABLE_FILE_VALIDATION: string;
		LSCOLORS: string;
		FNM_VERSION_FILE_STRATEGY: string;
		all_proxy: string;
		ALL_PROXY: string;
		FNM_ARCH: string;
		GRPC_PROXY: string;
		PATH: string;
		RSYNC_PROXY: string;
		npm_package_json: string;
		_: string;
		LaunchInstanceID: string;
		npm_config_userconfig: string;
		npm_config_init_module: string;
		USER_ZDOTDIR: string;
		__CFBundleIdentifier: string;
		npm_command: string;
		GVM_VERSION: string;
		PWD: string;
		npm_lifecycle_event: string;
		EDITOR: string;
		npm_package_name: string;
		LANG: string;
		gvm_pkgset_name: string;
		BUNDLED_DEBUGPY_PATH: string;
		CURSOR_CLI_MODE: string;
		npm_config_npm_version: string;
		VSCODE_GIT_ASKPASS_EXTRA_ARGS: string;
		XPC_FLAGS: string;
		FNM_MULTISHELL_PATH: string;
		npm_config_node_gyp: string;
		JAVA_TOOL_OPTIONS: string;
		https_proxy: string;
		HTTPS_PROXY: string;
		npm_package_version: string;
		XPC_SERVICE_NAME: string;
		SANDBOX_RUNTIME: string;
		VSCODE_INJECTION: string;
		VSCODE_DEBUGPY_ADAPTER_ENDPOINTS: string;
		HOME: string;
		SHLVL: string;
		GOROOT: string;
		VSCODE_GIT_ASKPASS_MAIN: string;
		CLOUDSDK_PROXY_TYPE: string;
		TMPPREFIX: string;
		CLAUDE_CODE_EXECPATH: string;
		no_proxy: string;
		HOMEBREW_PREFIX: string;
		GIT_SSH_COMMAND: string;
		HTTP_PROXY: string;
		gvm_go_name: string;
		FNM_DIR: string;
		npm_config_cache: string;
		LESS: string;
		LOGNAME: string;
		npm_lifecycle_script: string;
		GVM_OVERLAY_PREFIX: string;
		CLAUDE_CODE_TMPDIR: string;
		VSCODE_GIT_IPC_HANDLE: string;
		COREPACK_ENABLE_AUTO_PIN: string;
		GOPATH: string;
		BUN_INSTALL: string;
		GITHUB_TOKEN: string;
		PKG_CONFIG_PATH: string;
		npm_config_user_agent: string;
		FNM_RESOLVE_ENGINES: string;
		CLAUDE_CODE_SESSION_ID: string;
		VSCODE_GIT_ASKPASS_NODE: string;
		GIT_ASKPASS: string;
		HOMEBREW_CELLAR: string;
		INFOPATH: string;
		grpc_proxy: string;
		CLAUDECODE: string;
		SECURITYSESSIONID: string;
		VIRTUAL_ENV_PROMPT: string;
		npm_node_execpath: string;
		npm_config_prefix: string;
		COLORTERM: string;
		GVM_PATH_BACKUP: string;
		NODE_ENV: string;
		[key: `PUBLIC_${string}`]: undefined;
		[key: `${string}`]: string | undefined;
	}
}

/**
 * This module provides access to environment variables set _dynamically_ at runtime and that are _publicly_ accessible.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Dynamic environment variables are defined by the platform you're running on. For example if you're using [`adapter-node`](https://github.com/sveltejs/kit/tree/main/packages/adapter-node) (or running [`vite preview`](https://svelte.dev/docs/kit/cli)), this is equivalent to `process.env`.
 * 
 * **_Public_ access:**
 * 
 * - This module _can_ be imported into client-side code
 * - **Only** variables that begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) (which defaults to `PUBLIC_`) are included
 * 
 * > [!NOTE] In `dev`, `$env/dynamic` includes environment variables from `.env`. In `prod`, this behavior will depend on your adapter.
 * 
 * > [!NOTE] To get correct types, environment variables referenced in your code should be declared (for example in an `.env` file), even if they don't have a value until the app is deployed:
 * >
 * > ```env
 * > MY_FEATURE_FLAG=
 * > ```
 * >
 * > You can override `.env` values from the command line like so:
 * >
 * > ```sh
 * > MY_FEATURE_FLAG="enabled" npm run dev
 * > ```
 * 
 * For example, given the following runtime environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://example.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { env } from '$env/dynamic/public';
 * console.log(env.ENVIRONMENT); // => undefined, not public
 * console.log(env.PUBLIC_BASE_URL); // => "http://example.com"
 * ```
 * 
 * ```
 * 
 * ```
 */
declare module '$env/dynamic/public' {
	export const env: {
		[key: `PUBLIC_${string}`]: string | undefined;
	}
}
