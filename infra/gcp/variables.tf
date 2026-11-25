variable "project" {
  type        = string
  description = "GCP project id"
}

variable "region" {
  type        = string
  default     = "europe-west3"
  description = "Frankfurt, to keep data in the EU"
}

variable "image" {
  type        = string
  description = "Container image of the pipeline (Dockerfile at the repository root)"
}

variable "deid_key_secret" {
  type        = string
  description = "Secret Manager secret holding the de-identification key"
}

variable "drop_retention_days" {
  type    = number
  default = 30
}

variable "evidence_retention_seconds" {
  type    = number
  default = 315360000 # 10 years
}
