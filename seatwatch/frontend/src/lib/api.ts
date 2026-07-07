export type Showtime = {
	id: number;
	movieSlug: string;
	movieTitle: string;
	format: string;
	showAt: string;
	status: string;
};

export type Seat = {
	available: boolean;
	column: number;
	row: number;
	name: string;
	type: string;
	seatTier: string;
	shouldDisplay: boolean;
};

export type SeatingLayout = {
	columns: number;
	rows: number;
	seats: Seat[];
};

export type ScreeningResult = {
	showtimeId: number;
	showAt: string;
	format: string;
	status: string;
	matched: boolean;
	openSeats: number;
	groupCount: number;
	seatGroups: string[][];
};

export type EvaluateResponse = {
	results: ScreeningResult[];
	pending: number;
	refreshedAt: string;
};

export type Watch = {
	id: number;
	email: string;
	movieSlug: string;
	movieTitle: string;
	format: string;
	numSeats: number;
	seats: string[];
	dateFrom: string;
	dateTo: string;
	createdAt: string;
	matches?: ScreeningResult[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(path, init);
	if (!res.ok) {
		const body = await res.json().catch(() => ({ error: res.statusText }));
		throw new Error(body.error ?? res.statusText);
	}
	if (res.status === 204) return undefined as T;
	return res.json();
}

export const api = {
	config: () => request<{ alertsEnabled: boolean }>('/api/config'),
	showtimes: () => request<Showtime[]>('/api/showtimes'),
	seatMap: (showtimeId: number) => request<SeatingLayout>(`/api/seatmap/${showtimeId}`),
	evaluate: (body: {
		movieSlug: string;
		format: string;
		numSeats: number;
		seats: string[];
		dateFrom: string;
		dateTo: string;
	}) =>
		request<EvaluateResponse>('/api/evaluate', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(body)
		}),
	createWatch: (body: {
		email: string;
		movieSlug: string;
		movieTitle: string;
		format: string;
		numSeats: number;
		seats: string[];
		dateFrom: string;
		dateTo: string;
	}) =>
		request<{ watch: Watch; evaluation: EvaluateResponse }>('/api/watches', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(body)
		}),
	listWatches: (email: string) => request<Watch[]>(`/api/watches?email=${encodeURIComponent(email)}`),
	deleteWatch: (id: number) => request<void>(`/api/watches/${id}`, { method: 'DELETE' })
};

export function fmtShowtime(iso: string): string {
	return new Date(iso).toLocaleString('en-US', {
		weekday: 'short',
		month: 'short',
		day: 'numeric',
		hour: 'numeric',
		minute: '2-digit'
	});
}

export function amcBookingURL(showtimeId: number): string {
	return `https://www.amctheatres.com/showtimes/${showtimeId}/seats`;
}

export function localDate(iso: string): string {
	return new Date(iso).toLocaleDateString('en-CA');
}
