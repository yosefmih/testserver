{{- define "paddleocr-vl.name" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "paddleocr-vl.labels" -}}
app.kubernetes.io/name: paddleocr-vl
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{- define "paddleocr-vl.selectorLabels" -}}
app.kubernetes.io/name: paddleocr-vl
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
