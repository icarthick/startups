# acme-store Heroku Terraform — discover-phase fixture.
# Exercises: app + 2 formations + 3 addons (postgres/redis/papertrail) +
# config_association (secret redaction) + pipeline (detect-only) + space.

resource "heroku_app" "web_app" {
  name   = "acme-store"
  region = "us"
  stack  = "heroku-22"

  organization {
    name = "acme-inc"
  }

  buildpacks = ["heroku/ruby"]
}

resource "heroku_formation" "web" {
  app_id   = heroku_app.web_app.id
  type     = "web"
  quantity = 2
  size     = "standard-2x"
}

resource "heroku_formation" "worker" {
  app_id   = heroku_app.web_app.id
  type     = "worker"
  quantity = 1
  size     = "standard-1x"
}

resource "heroku_addon" "postgres" {
  app_id = heroku_app.web_app.id
  plan   = "heroku-postgresql:standard-0"
}

resource "heroku_addon" "redis" {
  app_id = heroku_app.web_app.id
  plan   = "heroku-redis:premium-2"
}

resource "heroku_addon" "papertrail" {
  app_id = heroku_app.web_app.id
  plan   = "papertrail:choklad"
}

resource "heroku_config_association" "config" {
  app_id = heroku_app.web_app.id
  vars = {
    DATABASE_URL = "postgres://redacted"
    REDIS_URL    = "redis://redacted"
    SECRET_KEY   = "super-secret-value"
  }
}

resource "heroku_pipeline" "main" {
  name = "acme-pipeline"
}

resource "heroku_space" "private" {
  name         = "acme-space"
  organization = "acme-inc"
  region       = "virginia"
  shield       = false
}
