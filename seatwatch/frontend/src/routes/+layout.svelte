<script lang="ts">
	import '../app.css';
	import { api } from '$lib/api';
	let { children } = $props();
	let alertsEnabled = $state(false);
	$effect(() => {
		api.config().then((c) => (alertsEnabled = c.alertsEnabled)).catch(() => {});
	});
</script>

<div class="mx-auto max-w-4xl px-4 pb-24">
	<header class="flex items-baseline justify-between py-8">
		<a href="/" class="font-display text-4xl tracking-wide text-marquee">SEATWATCH</a>
		<nav class="flex items-baseline gap-6 text-sm text-dim">
			<span class="hidden sm:inline">AMC Lincoln Square 13 · New York</span>
			{#if alertsEnabled}
				<a href="/watches" class="border-b border-dotted border-dim hover:text-marquee">my watches</a>
			{/if}
		</nav>
	</header>
	{@render children()}

	<footer class="mt-16 flex justify-center pb-4">
		<a
			href="https://www.porter.run/"
			target="_blank"
			rel="noreferrer"
			class="flex items-center gap-2 rounded-full border border-line px-3 py-1.5 text-xs text-dim transition-colors hover:border-marquee/50 hover:text-current"
		>
			<span>Powered by</span>
			<svg viewBox="0 0 312 52" class="h-3 w-auto" aria-label="Porter">
				<rect width="312" height="52" fill="#FFFBE1" />
				<path
					d="M7.28003 52V0H27.7223C38.3547 0 44.72 5.34868 44.72 14.8574C44.72 24.2914 38.3552 29.7144 27.7223 29.7144H14.7675V52H7.28003ZM14.7675 23.4H27.7218C34.2358 23.4 37.231 20.2056 37.231 14.8569C37.231 9.43396 34.2358 6.3139 27.7218 6.3139H14.7675V23.4Z"
					fill="black"
				/>
				<path d="M62.4 0H52V10.4H62.4V0Z" fill="black" />
				<path d="M58.5 3.8999H55.9V6.4999H58.5V3.8999Z" fill="#FFFBE1" />
				<path d="M104 0H93.6V10.4H104V0Z" fill="black" />
				<path d="M100.1 3.8999H97.5V6.4999H100.1V3.8999Z" fill="#FFFBE1" />
				<path d="M104 41.6001H93.6V52.0001H104V41.6001Z" fill="black" />
				<path d="M100.1 45.5H97.5V48.1H100.1V45.5Z" fill="#FFFBE1" />
				<path d="M62.4 41.6001H52V52.0001H62.4V41.6001Z" fill="black" />
				<path d="M58.5 45.5H55.9V48.1H58.5V45.5Z" fill="#FFFBE1" />
				<path d="M72.8 31.2002H62.4V41.6002H72.8V31.2002Z" fill="black" />
				<path d="M68.9 35.1001H66.3V37.7001H68.9V35.1001Z" fill="#FFFBE1" />
				<path d="M72.8 20.7998H62.4V31.1998H72.8V20.7998Z" fill="black" />
				<path d="M68.9 24.6997H66.3V27.2997H68.9V24.6997Z" fill="#FFFBE1" />
				<path d="M72.8 10.3999H62.4V20.7999H72.8V10.3999Z" fill="black" />
				<path d="M68.9 14.2998H66.3V16.8998H68.9V14.2998Z" fill="#FFFBE1" />
				<path d="M83.2 10.3999H72.8V20.7999H83.2V10.3999Z" fill="black" />
				<path d="M79.3001 14.2998H76.7001V16.8998H79.3001V14.2998Z" fill="#FFFBE1" />
				<path d="M93.6 10.3999H83.2V20.7999H93.6V10.3999Z" fill="black" />
				<path d="M89.7 14.2998H87.1V16.8998H89.7V14.2998Z" fill="#FFFBE1" />
				<path d="M93.6 20.7998H83.2V31.1998H93.6V20.7998Z" fill="black" />
				<path d="M89.7 24.6997H87.1V27.2997H89.7V24.6997Z" fill="#FFFBE1" />
				<path d="M93.6 31.2002H83.2V41.6002H93.6V31.2002Z" fill="black" />
				<path d="M89.7 35.1001H87.1V37.7001H89.7V35.1001Z" fill="#FFFBE1" />
				<path d="M83.2 31.2002H72.8V41.6002H83.2V31.2002Z" fill="black" />
				<path d="M79.3001 35.1001H76.7001V37.7001H79.3001V35.1001Z" fill="#FFFBE1" />
				<path
					d="M120.821 29.7144H118.799V52H111.312V0H131.753C142.386 0 148.751 5.34868 148.751 14.8574C148.751 25.4057 140.889 29.7144 132.053 29.7144H129.732L150.249 52H140.514L120.821 29.7144ZM118.799 23.4H131.753C138.267 23.4 141.262 20.2056 141.262 14.8569C141.262 9.43396 138.267 6.3139 131.753 6.3139H118.799V23.4Z"
					fill="black"
				/>
				<path
					d="M178.256 6.31441H161.782V0H202.217V6.31441H185.744V52H178.256V6.31441Z"
					fill="black"
				/>
				<path
					d="M215.348 52V0H249.792V6.31441H222.835V21.9142H248.294V28.2281H222.835V45.6856H249.792V51.9995L215.348 52Z"
					fill="black"
				/>
				<path
					d="M276.041 29.7144H274.018V52H266.531V0H286.973C297.606 0 303.971 5.34868 303.971 14.8574C303.971 25.4057 296.109 29.7144 287.273 29.7144H284.951L305.469 52H295.734L276.041 29.7144H276.041ZM274.018 23.4H286.973C293.487 23.4 296.482 20.2056 296.482 14.8569C296.482 9.43396 293.487 6.3139 286.973 6.3139H274.018V23.4Z"
					fill="black"
				/>
			</svg>
		</a>
	</footer>
</div>
