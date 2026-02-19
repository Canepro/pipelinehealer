{{- define "pipelinehealer.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "pipelinehealer.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "pipelinehealer.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "pipelinehealer.labels" -}}
helm.sh/chart: {{ include "pipelinehealer.chart" . }}
app.kubernetes.io/name: {{ include "pipelinehealer.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "pipelinehealer.selectorLabels" -}}
app.kubernetes.io/name: {{ include "pipelinehealer.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "pipelinehealer.backend.fullname" -}}
{{- printf "%s-backend" (include "pipelinehealer.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "pipelinehealer.frontend.fullname" -}}
{{- printf "%s-frontend" (include "pipelinehealer.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "pipelinehealer.backend.image" -}}
{{/* Digest takes precedence to keep releases immutable and reproducible. */}}
{{- $digest := .Values.backend.image.digest | default "" -}}
{{- if $digest -}}
{{- printf "%s@%s" .Values.backend.image.repository $digest -}}
{{- else -}}
{{- $tag := .Values.backend.image.tag | default .Chart.AppVersion -}}
{{- printf "%s:%s" .Values.backend.image.repository $tag -}}
{{- end -}}
{{- end -}}

{{- define "pipelinehealer.frontend.image" -}}
{{/* Digest takes precedence to keep releases immutable and reproducible. */}}
{{- $digest := .Values.frontend.image.digest | default "" -}}
{{- if $digest -}}
{{- printf "%s@%s" .Values.frontend.image.repository $digest -}}
{{- else -}}
{{- $tag := .Values.frontend.image.tag | default .Chart.AppVersion -}}
{{- printf "%s:%s" .Values.frontend.image.repository $tag -}}
{{- end -}}
{{- end -}}
