<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getProject, getMe, listMembers, addMember, updateMemberRole, removeMember, listInvites, revokeInvite, type Member, type Invite } from '$lib/api';

	let project = $state<any>(null);
	let me = $state<any>(null);
	let members = $state<Member[]>([]);
	let invites = $state<Invite[]>([]);
	let isAdmin = $state(false);
	let newEmail = $state('');
	let newRole = $state('developer');
	let adding = $state(false);
	let message = $state('');
	let error = $state('');
	let inviteUrl = $state('');

	const projectId = page.params.id;

	onMount(async () => {
		[project, me] = await Promise.all([getProject(projectId), getMe()]);
		isAdmin = project.role === 'admin';
		await loadMembers();
	});

	async function loadMembers() {
		[members, invites] = await Promise.all([
			listMembers(projectId),
			isAdmin ? listInvites(projectId) : Promise.resolve([]),
		]);
	}

	async function handleAdd() {
		if (!newEmail.trim()) return;
		adding = true;
		error = '';
		message = '';
		inviteUrl = '';
		try {
			const result = await addMember(projectId, newEmail.trim(), newRole);
			newEmail = '';
			newRole = 'developer';
			if (result.status === 'invited') {
				message = `Invite sent to ${result.email}`;
				inviteUrl = result.invite_url || '';
			} else {
				message = 'Member added';
			}
			await loadMembers();
		} catch (e: any) {
			error = e.message;
		}
		adding = false;
	}

	async function handleRoleChange(member: Member, role: string) {
		error = '';
		message = '';
		inviteUrl = '';
		try {
			await updateMemberRole(projectId, member.id, role);
			message = `Updated ${member.name || member.email} to ${role}`;
			await loadMembers();
		} catch (e: any) {
			error = e.message;
		}
	}

	async function handleRemove(member: Member) {
		if (!confirm(`Remove ${member.name || member.email} from this project?`)) return;
		error = '';
		message = '';
		inviteUrl = '';
		try {
			await removeMember(projectId, member.id);
			message = `Removed ${member.name || member.email}`;
			await loadMembers();
		} catch (e: any) {
			error = e.message;
		}
	}

	async function handleRevoke(invite: Invite) {
		if (!confirm(`Revoke invite for ${invite.email}?`)) return;
		error = '';
		message = '';
		inviteUrl = '';
		try {
			await revokeInvite(projectId, invite.id);
			message = `Invite for ${invite.email} revoked`;
			await loadMembers();
		} catch (e: any) {
			error = e.message;
		}
	}

	function copyInviteUrl() {
		navigator.clipboard.writeText(inviteUrl);
		message = 'Invite link copied to clipboard';
	}
</script>

{#if project}
<div class="min-h-screen">
	<header class="border-b border-warm-700/50 px-8 py-4">
		<div class="max-w-5xl mx-auto flex items-center justify-between">
			<a href="/" class="font-serif text-2xl text-cream hover:text-cream no-underline">Autopilot</a>
		</div>
	</header>

	<main class="max-w-5xl mx-auto px-8 py-12">
		<div class="mb-8">
			<a href="/projects/{projectId}" class="text-warm-500 text-sm hover:text-cream transition-colors duration-200 no-underline">&larr; Back to project</a>
		</div>

		<h1 class="font-serif text-3xl tracking-tight mb-12">{project.name} <span class="text-warm-500">&mdash;</span> Members</h1>

		{#if error}
			<div class="border border-red-900/50 bg-red-900/10 px-4 py-3 text-red-400 text-sm mb-6">{error}</div>
		{/if}
		{#if message}
			<div class="text-success text-sm mb-6">
				{message}
				{#if inviteUrl}
					<button
						class="ml-3 text-accent text-xs hover:text-cream transition-colors duration-200 underline"
						onclick={copyInviteUrl}
					>
						Copy invite link
					</button>
				{/if}
			</div>
		{/if}

		<!-- Add Member (admin only) -->
		{#if isAdmin}
		<section class="mb-10">
			<h2 class="text-xs text-warm-500 uppercase tracking-wider mb-4">Add Member</h2>
			<div class="border border-warm-700/50 px-6 py-5">
				<div class="flex items-end gap-4">
					<div class="flex-1">
						<label class="text-warm-500 text-xs uppercase tracking-wider block mb-2">Email</label>
						<input
							type="email"
							bind:value={newEmail}
							placeholder="user@example.com"
							class="w-full bg-transparent border border-warm-600 px-4 py-2.5 text-sm text-cream focus:outline-none focus:border-accent transition-colors duration-200"
						/>
					</div>
					<div class="w-40">
						<label class="text-warm-500 text-xs uppercase tracking-wider block mb-2">Role</label>
						<select
							bind:value={newRole}
							class="w-full bg-transparent border border-warm-600 px-4 py-2.5 text-sm text-cream focus:outline-none focus:border-accent transition-colors duration-200"
						>
							<option value="developer">Developer</option>
							<option value="admin">Admin</option>
						</select>
					</div>
					<button
						class="bg-accent/10 border border-accent text-accent px-5 py-2.5 text-sm hover:bg-accent/20 transition-all duration-200 disabled:opacity-50 whitespace-nowrap"
						onclick={handleAdd}
						disabled={adding || !newEmail.trim()}
					>
						{adding ? 'Adding...' : 'Add Member'}
					</button>
				</div>
				<p class="text-warm-500 text-xs mt-3">
					If the user hasn't signed in yet, they'll receive an invite link to join.
				</p>
			</div>
		</section>
		{/if}

		<!-- Pending Invites -->
		{#if isAdmin && invites.length > 0}
		<section class="mb-10">
			<h2 class="text-xs text-warm-500 uppercase tracking-wider mb-4">Pending Invites ({invites.length})</h2>
			<div class="border border-warm-700/50 divide-y divide-warm-700/50">
				{#each invites as invite}
					<div class="px-6 py-4 flex items-center justify-between">
						<div class="flex items-center gap-3">
							<div class="w-8 h-8 rounded-full bg-warm-700/50 border border-dashed border-warm-600 flex items-center justify-center text-warm-500 text-xs">
								{invite.email[0].toUpperCase()}
							</div>
							<div>
								<div class="text-cream text-sm">{invite.email}</div>
								<div class="text-warm-500 text-xs">
									Invited by {invite.invited_by} &middot; Expires {new Date(invite.expires_at).toLocaleDateString()}
								</div>
							</div>
						</div>
						<div class="flex items-center gap-3">
							<span class="text-warm-500 text-xs px-3 py-1.5 border border-warm-700/50 capitalize">{invite.role}</span>
							<button
								class="text-warm-500 text-xs hover:text-red-400 transition-colors duration-200"
								onclick={() => handleRevoke(invite)}
							>
								Revoke
							</button>
						</div>
					</div>
				{/each}
			</div>
		</section>
		{/if}

		<!-- Members List -->
		<section>
			<h2 class="text-xs text-warm-500 uppercase tracking-wider mb-4">Team ({members.length})</h2>
			<div class="border border-warm-700/50 divide-y divide-warm-700/50">
				{#each members as member}
					<div class="px-6 py-4 flex items-center justify-between">
						<div class="flex items-center gap-3">
							{#if member.avatar_url}
								<img src={member.avatar_url} alt="" class="w-8 h-8 rounded-full" />
							{:else}
								<div class="w-8 h-8 rounded-full bg-warm-700 flex items-center justify-center text-warm-400 text-xs font-medium">
									{(member.name || member.email)[0].toUpperCase()}
								</div>
							{/if}
							<div>
								<div class="text-cream text-sm">
									{member.name || member.email}
									{#if me && member.user_id === me.id}
										<span class="text-warm-500 text-xs ml-1">(you)</span>
									{/if}
								</div>
								{#if member.name}
									<div class="text-warm-500 text-xs">{member.email}</div>
								{/if}
							</div>
						</div>
						<div class="flex items-center gap-3">
							{#if isAdmin && me && member.user_id !== me.id}
								<select
									value={member.role}
									onchange={(e) => handleRoleChange(member, e.currentTarget.value)}
									class="bg-transparent border border-warm-600 px-3 py-1.5 text-xs text-cream focus:outline-none focus:border-accent transition-colors duration-200"
								>
									<option value="developer">Developer</option>
									<option value="admin">Admin</option>
								</select>
								<button
									class="text-warm-500 text-xs hover:text-red-400 transition-colors duration-200"
									onclick={() => handleRemove(member)}
								>
									Remove
								</button>
							{:else}
								<span class="text-warm-500 text-xs px-3 py-1.5 border border-warm-700/50 capitalize">{member.role}</span>
							{/if}
						</div>
					</div>
				{/each}

				{#if members.length === 0}
					<div class="px-6 py-8 text-center text-warm-500 text-sm">No members yet.</div>
				{/if}
			</div>
		</section>
	</main>
</div>
{/if}
