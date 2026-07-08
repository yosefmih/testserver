package main

import (
	"context"
	"log"
	"os"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.24.0"
)

// initTracing wires the OTel SDK when OTEL_EXPORTER_OTLP_ENDPOINT is set
// (e.g. http://otel-collector.telemetry.svc:4318) and is a no-op otherwise,
// so local runs stay untraced without configuration.
func initTracing(ctx context.Context) func() {
	if os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT") == "" {
		return func() {}
	}
	exporter, err := otlptracehttp.New(ctx)
	if err != nil {
		log.Printf("otel exporter init failed, tracing disabled: %v", err)
		return func() {}
	}
	serviceName := os.Getenv("OTEL_SERVICE_NAME")
	if serviceName == "" {
		serviceName = "seatwatcher"
	}
	res, _ := resource.Merge(resource.Default(),
		resource.NewWithAttributes(semconv.SchemaURL, semconv.ServiceName(serviceName)))
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
	)
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{}, propagation.Baggage{}))
	log.Printf("tracing enabled: exporting to %s as %s", os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT"), serviceName)
	return func() {
		if err := tp.Shutdown(context.Background()); err != nil {
			log.Printf("otel shutdown: %v", err)
		}
	}
}
