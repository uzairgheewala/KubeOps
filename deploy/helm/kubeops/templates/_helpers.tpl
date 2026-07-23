{{- define "kubeops.name" -}}{{ default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}{{- end }}
{{- define "kubeops.fullname" -}}{{ default (printf "%s-%s" .Release.Name (include "kubeops.name" .)) .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}{{- end }}
{{- define "kubeops.labels" -}}
app.kubernetes.io/name: {{ include "kubeops.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
{{- define "kubeops.serviceAccountName" -}}{{ default (include "kubeops.fullname" .) .Values.serviceAccount.name }}{{- end }}
