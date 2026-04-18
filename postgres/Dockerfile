FROM postgres:16-alpine
COPY pg_hba.conf /etc/postgresql/pg_hba.conf
CMD ["postgres", "-c", "hba_file=/etc/postgresql/pg_hba.conf"]
