package main

import (
	"fmt"
	"log"
	"net/smtp"
	"os"
	"strings"
)

type Mailer struct {
	host string
	port string
	user string
	pass string
	from string
}

func NewMailerFromEnv() *Mailer {
	return &Mailer{
		host: os.Getenv("SMTP_HOST"),
		port: envOr("SMTP_PORT", "587"),
		user: os.Getenv("SMTP_USER"),
		pass: os.Getenv("SMTP_PASS"),
		from: envOr("SMTP_FROM", os.Getenv("SMTP_USER")),
	}
}

func (m *Mailer) SendMatchAlert(watch Watch, matches []ScreeningResult) error {
	subject := fmt.Sprintf("Seats available: %s (%d found)", watch.MovieTitle, len(matches))
	body := m.composeBody(watch, matches)

	if m.host == "" {
		log.Printf("ALERT (SMTP not configured, would email %s)\nSubject: %s\n%s", watch.Email, subject, body)
		return nil
	}

	msg := strings.Join([]string{
		"From: " + m.from,
		"To: " + watch.Email,
		"Subject: " + subject,
		"Content-Type: text/plain; charset=utf-8",
		"",
		body,
	}, "\r\n")

	var auth smtp.Auth
	if m.user != "" {
		auth = smtp.PlainAuth("", m.user, m.pass, m.host)
	}
	return smtp.SendMail(m.host+":"+m.port, auth, m.from, []string{watch.Email}, []byte(msg))
}

func (m *Mailer) composeBody(watch Watch, matches []ScreeningResult) string {
	var b strings.Builder
	fmt.Fprintf(&b, "Good news! Screenings of %s now have %d adjacent seat(s) from your list.\n\n", watch.MovieTitle, watch.NumSeats)
	for _, match := range matches {
		fmt.Fprintf(&b, "• %s", match.ShowAt.Local().Format("Mon Jan 2, 3:04 PM"))
		if match.Format != "" {
			fmt.Fprintf(&b, " (%s)", match.Format)
		}
		b.WriteString("\n")
		fmt.Fprintf(&b, "    %d of your seats open, %d ways to sit %d together\n", match.OpenSeats, match.GroupCount, watch.NumSeats)
		for _, group := range match.SeatGroups {
			fmt.Fprintf(&b, "    best seats: %s\n", strings.Join(group, ", "))
		}
		fmt.Fprintf(&b, "    book: https://www.amctheatres.com/showtimes/%d/seats\n\n", match.ShowtimeID)
	}
	b.WriteString("Seats sell fast — book soon!\n")
	return b.String()
}
