{{- define "sibr.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 40 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 40 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "sibr.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "sibr.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "sibr.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/* Container-spec for ett steg. Kall med (dict "root" $ "name" "scraping") */}}
{{- define "sibr.container" -}}
{{- $root := .root -}}
{{- $step := index $root.Values.steps .name | required (printf "steps.%s er ikke definert i values" .name) -}}
- name: {{ .name }}
  image: "{{ $root.Values.image.registry }}/{{ $root.Values.image.prefix }}{{ $step.image }}:{{ $step.tag | default $root.Values.image.tag }}"
  imagePullPolicy: {{ $root.Values.image.pullPolicy }}
  {{- with $step.args }}
  args:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  env:
    {{- range $k, $v := $root.Values.env }}
    - name: {{ $k }}
      value: {{ $v | quote }}
    {{- end }}
    {{- range $k, $v := $step.env }}
    - name: {{ $k }}
      value: {{ $v | quote }}
    {{- end }}
  {{- with $step.secretName }}
  envFrom:
    - secretRef:
        name: {{ . }}
  {{- end }}
  resources:
    {{- toYaml $step.resources | nindent 4 }}
  securityContext:
    {{- toYaml $root.Values.containerSecurityContext | nindent 4 }}
{{- end -}}

{{/* Felles pod-felter */}}
{{- define "sibr.podCommon" -}}
restartPolicy: Never
serviceAccountName: {{ include "sibr.serviceAccountName" . }}
automountServiceAccountToken: false
{{- $pull := .Values.imagePullSecrets | default list }}
{{- if (.Values.imageCredentials | default dict).password }}
{{- $pull = append $pull (dict "name" (printf "%s-registry" (include "sibr.fullname" .))) }}
{{- end }}
{{- with $pull }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
securityContext:
  {{- toYaml .Values.podSecurityContext | nindent 2 }}
{{- with .Values.tolerations }}
tolerations:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.nodeSelector }}
nodeSelector:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.affinity }}
affinity:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end -}}
