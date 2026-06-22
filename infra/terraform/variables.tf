variable "region" {
  description = "AWS region (free tier applies in all regions)"
  type        = string
  default     = "ap-northeast-2" # Seoul
}

variable "project" {
  description = "Name prefix for tagging/identifying resources"
  type        = string
  default     = "football"
}

variable "db_name" {
  description = "Initial database name created on the RDS instance"
  type        = string
  default     = "football"
}

variable "db_username" {
  description = "RDS master username"
  type        = string
  default     = "footballadmin"
}

variable "db_password" {
  description = "RDS master password (inject via terraform.tfvars or TF_VAR_db_password — never hardcode)"
  type        = string
  sensitive   = true
}

variable "my_ip" {
  description = "Your public IP in CIDR form (e.g. 1.2.3.4/32). Only this IP may reach port 5432."
  type        = string
}

variable "engine_version" {
  description = "PostgreSQL major.minor (must support pgvector; 16.x ok). Adjust if AWS reports it unavailable."
  type        = string
  default     = "16.9"
}
