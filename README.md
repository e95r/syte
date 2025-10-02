# syte

## Development environment notes

- The PostgreSQL container runs on the `postgres:16-alpine` image to match the
  persisted database volume. Update your local images accordingly before
  starting the stack.
- Run `docker compose down -v` **only** when you intentionally want to remove
  the database volume and rebuild it from scratch. This command deletes all
  persisted data.
