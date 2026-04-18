FROM postgres:16-alpine
COPY entrypoint.sh /usr/local/bin/pg-entrypoint.sh
RUN sed -i 's/\r//' /usr/local/bin/pg-entrypoint.sh && \
    chmod +x /usr/local/bin/pg-entrypoint.sh
ENTRYPOINT ["pg-entrypoint.sh"]
CMD ["postgres"]
