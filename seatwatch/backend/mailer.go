package main

import (
	"fmt"
	"html"
	"log"
	"net/mail"
	"net/smtp"
	"net/url"
	"os"
	"strings"
)

type Mailer struct {
	host          string
	port          string
	user          string
	pass          string
	from          string // full header value, e.g. "SeatWatch <onboarding@resend.dev>"
	envelopeFrom  string // bare address only; SMTP's MAIL FROM doesn't accept a display name
	publicBaseURL string // e.g. https://seatwatcher.jemy.withporter.run; links back to our own site
}

func NewMailerFromEnv() *Mailer {
	from := envOr("SMTP_FROM", os.Getenv("SMTP_USER"))
	envelopeFrom := from
	if addr, err := mail.ParseAddress(from); err == nil {
		envelopeFrom = addr.Address
	}
	return &Mailer{
		host:          os.Getenv("SMTP_HOST"),
		port:          envOr("SMTP_PORT", "587"),
		user:          os.Getenv("SMTP_USER"),
		pass:          os.Getenv("SMTP_PASS"),
		from:          from,
		envelopeFrom:  envelopeFrom,
		publicBaseURL: strings.TrimSuffix(os.Getenv("PUBLIC_BASE_URL"), "/"),
	}
}

// watchesURL links to the watcher's own results page, deep-linked with their
// email, rather than a specific screening: seats sell out the moment someone
// else books, so the email should point at a live page, not a stale snapshot.
func (m *Mailer) watchesURL(email string) string {
	if m.publicBaseURL == "" {
		return ""
	}
	return fmt.Sprintf("%s/watches?email=%s", m.publicBaseURL, url.QueryEscape(email))
}

func (m *Mailer) SendMatchAlert(watch Watch, matches []ScreeningResult) error {
	subject := fmt.Sprintf("Seats available: %s (%d found)", watch.MovieTitle, len(matches))
	text := m.composeText(watch, matches)
	htmlBody := m.composeHTML(watch, matches)

	if m.host == "" {
		log.Printf("ALERT (SMTP not configured, would email %s)\nSubject: %s\n%s", watch.Email, subject, text)
		return nil
	}

	const boundary = "seatwatch-boundary"
	var b strings.Builder
	fmt.Fprintf(&b, "From: %s\r\n", m.from)
	fmt.Fprintf(&b, "To: %s\r\n", watch.Email)
	fmt.Fprintf(&b, "Subject: %s\r\n", subject)
	b.WriteString("MIME-Version: 1.0\r\n")
	fmt.Fprintf(&b, "Content-Type: multipart/alternative; boundary=\"%s\"\r\n\r\n", boundary)

	fmt.Fprintf(&b, "--%s\r\n", boundary)
	b.WriteString("Content-Type: text/plain; charset=utf-8\r\n\r\n")
	b.WriteString(text)
	b.WriteString("\r\n\r\n")

	fmt.Fprintf(&b, "--%s\r\n", boundary)
	b.WriteString("Content-Type: text/html; charset=utf-8\r\n\r\n")
	b.WriteString(htmlBody)
	b.WriteString("\r\n\r\n")

	fmt.Fprintf(&b, "--%s--\r\n", boundary)

	var auth smtp.Auth
	if m.user != "" {
		auth = smtp.PlainAuth("", m.user, m.pass, m.host)
	}
	return smtp.SendMail(m.host+":"+m.port, auth, m.envelopeFrom, []string{watch.Email}, []byte(b.String()))
}

func (m *Mailer) composeText(watch Watch, matches []ScreeningResult) string {
	var b strings.Builder
	fmt.Fprintf(&b, "Good news! %s now has %d of your seats open on %d screening(s).\n\n", watch.MovieTitle, watch.NumSeats, len(matches))
	for _, match := range matches {
		fmt.Fprintf(&b, "- %s", match.ShowAt.Local().Format("Mon Jan 2, 3:04 PM"))
		if match.Format != "" {
			fmt.Fprintf(&b, " (%s)", match.Format)
		}
		fmt.Fprintf(&b, " — %d open, %d ways to sit %d together\n", match.OpenSeats, match.GroupCount, watch.NumSeats)
	}
	b.WriteString("\n")
	if link := m.watchesURL(watch.Email); link != "" {
		fmt.Fprintf(&b, "See live seats and book: %s\n\n", link)
	}
	b.WriteString("Seats sell fast — check soon, availability may have changed since this email was sent.\n")
	return b.String()
}

func (m *Mailer) composeHTML(watch Watch, matches []ScreeningResult) string {
	const (
		ink    = "#0f0e0c"
		cream  = "#f5f1e6"
		marque = "#f2b90d"
		dim    = "#6b6558"
	)
	esc := html.EscapeString

	var rows strings.Builder
	for _, match := range matches {
		when := esc(match.ShowAt.Local().Format("Mon Jan 2, 3:04 PM"))
		format := ""
		if match.Format != "" {
			format = esc(match.Format) + " &middot; "
		}
		example := ""
		if len(match.SeatGroups) > 0 {
			example = " (e.g. " + esc(strings.Join(match.SeatGroups[0], ", ")) + ")"
		}
		fmt.Fprintf(&rows, `
			<tr>
				<td style="padding:14px 0;border-top:1px solid #e5e0d0;">
					<div style="font-size:15px;font-weight:600;color:%s;">%s</div>
					<div style="font-size:13px;color:%s;margin-top:2px;">%s%d of your seats open &middot; %d ways to sit %d together%s</div>
				</td>
			</tr>`, ink, when, dim, format, match.OpenSeats, match.GroupCount, watch.NumSeats, example)
	}

	ctaButton := ""
	if link := m.watchesURL(watch.Email); link != "" {
		ctaButton = fmt.Sprintf(`
			<tr>
				<td style="padding:24px 0 4px;text-align:center;">
					<a href="%s" style="display:inline-block;background:%s;color:%s;font-weight:700;font-size:15px;text-decoration:none;padding:12px 28px;border-radius:8px;">
						See live seats &amp; book &rarr;
					</a>
				</td>
			</tr>`, esc(link), marque, ink)
	}

	return fmt.Sprintf(`<!doctype html>
<html>
<body style="margin:0;padding:0;background:%s;font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;">
	<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" style="background:%s;">
		<tr>
			<td align="center" style="padding:32px 16px;">
				<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e0d0;">
					<tr>
						<td style="background:%s;padding:24px 28px;">
							<span style="color:%s;font-size:20px;font-weight:800;letter-spacing:0.08em;">SEATWATCH</span>
						</td>
					</tr>
					<tr>
						<td style="padding:28px 28px 4px;">
							<div style="font-size:11px;font-weight:700;letter-spacing:0.1em;color:%s;text-transform:uppercase;">Seat alert</div>
							<div style="font-size:22px;font-weight:800;color:%s;margin-top:6px;">%s</div>
						</td>
					</tr>
					<tr>
						<td style="padding:10px 28px 6px;">
							<p style="font-size:15px;line-height:1.55;color:%s;margin:0;">
								Good news — we found room for your party of <strong style="color:%s;">%d</strong> across <strong style="color:%s;">%d upcoming screening%s</strong>. Here's what's available right now — grab them before someone else does.
							</p>
						</td>
					</tr>
					<tr>
						<td style="padding:0 28px;">
							<table role="presentation" width="100%%" cellpadding="0" cellspacing="0">
								%s
							</table>
						</td>
					</tr>
					<tr>
						<td style="padding:8px 28px 28px;">
							<table role="presentation" width="100%%" cellpadding="0" cellspacing="0">
								%s
							</table>
							<div style="font-size:12px;color:%s;text-align:center;margin-top:20px;">
								Seats sell fast — availability may have changed since this email was sent.
							</div>
						</td>
					</tr>
				</table>
			</td>
		</tr>
	</table>
</body>
</html>`,
		cream, cream, ink, marque,
		marque, ink, esc(watch.MovieTitle),
		ink, marque, watch.NumSeats, marque, len(matches), pluralS(len(matches)),
		rows.String(),
		ctaButton, dim,
	)
}

func pluralS(n int) string {
	if n == 1 {
		return ""
	}
	return "s"
}
