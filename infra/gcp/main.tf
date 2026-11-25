# Storage, warehouse and a batch job for the pipeline on Google Cloud. Declared and validated in CI, not deployed.
terraform {
  required_version = ">= 1.6"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 6.0" }
  }
}

provider "google" {
  project = var.project
  region  = var.region
}

resource "google_service_account" "pipeline" {
  account_id   = "tep-pipeline"
  display_name = "Theranostics evidence pipeline"
}

# Site drops: identifiable data, short-lived, versioned.
resource "google_storage_bucket" "drop" {
  name                        = "${var.project}-tep-drop"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  versioning { enabled = true }
  lifecycle_rule {
    condition { age = var.drop_retention_days }
    action { type = "Delete" }
  }
}

# De-identified outputs and evidence packs: retained, not deletable before the retention period.
resource "google_storage_bucket" "evidence" {
  name                        = "${var.project}-tep-evidence"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  versioning { enabled = true }
  retention_policy {
    retention_period = var.evidence_retention_seconds
    is_locked        = false
  }
}

resource "google_bigquery_dataset" "quality" {
  dataset_id  = "tep_quality"
  location    = var.region
  description = "Per-series data quality, issues and features (de-identified)."
}

resource "google_bigquery_table" "series" {
  dataset_id          = google_bigquery_dataset.quality.dataset_id
  table_id            = "series"
  deletion_protection = true
  schema = jsonencode([
    { name = "site", type = "STRING", mode = "REQUIRED" },
    { name = "series", type = "STRING", mode = "REQUIRED" },
    { name = "status", type = "STRING", mode = "REQUIRED" },
    { name = "has_weight", type = "BOOL" },
    { name = "has_dose", type = "BOOL" },
    { name = "has_times", type = "BOOL" },
    { name = "blocking_issues", type = "INT64" },
    { name = "duplicate_instances", type = "INT64" },
    { name = "order_fixed", type = "BOOL" },
    { name = "liver_reference", type = "FLOAT64" },
  ])
}

resource "google_storage_bucket_iam_member" "read_drop" {
  bucket = google_storage_bucket.drop.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_storage_bucket_iam_member" "write_evidence" {
  bucket = google_storage_bucket.evidence.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_bigquery_dataset_iam_member" "write_quality" {
  dataset_id = google_bigquery_dataset.quality.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_cloud_run_v2_job" "ingest" {
  name     = "tep-ingest"
  location = var.region
  template {
    template {
      service_account = google_service_account.pipeline.email
      timeout         = "3600s"
      containers {
        image = var.image
        args  = ["ingest", "/drop", "/out"]
        env {
          name = "TEP_DEID_KEY"
          value_source {
            secret_key_ref {
              secret  = var.deid_key_secret
              version = "latest"
            }
          }
        }
        resources {
          limits = { cpu = "2", memory = "4Gi" }
        }
        volume_mounts {
          name       = "drop"
          mount_path = "/drop"
        }
        volume_mounts {
          name       = "out"
          mount_path = "/out"
        }
      }
      volumes {
        name = "drop"
        gcs {
          bucket    = google_storage_bucket.drop.name
          read_only = true
        }
      }
      volumes {
        name = "out"
        gcs {
          bucket = google_storage_bucket.evidence.name
        }
      }
    }
  }
}
