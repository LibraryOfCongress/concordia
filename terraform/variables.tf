variable "region" {
  type        = string
  description = "AWS Region"
  default     = "us-east-1"
}

variable "tags" {
  type        = map
  description = "Project, Creator, and Environment are tagged by default. Add other tags here."
  default     = {}
}

variable "creator" {
  type        = string
  description = "Resources will be tagged with Creator"
  default     = "rstorey@loc.gov"
}

variable "loc_transit_gateway_id" {
  type        = string
  default     = "tgw-00d6fb177559a5030"
  description = "Transit Gateway ID for the pre-configured Library TGW which will be used to access internal network resources"
}
