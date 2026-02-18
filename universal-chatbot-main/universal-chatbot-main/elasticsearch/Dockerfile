FROM elasticsearch:9.2.1

USER root

COPY backups /usr/share/elasticsearch/backups
COPY entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/*.sh && \
    chown elasticsearch:elasticsearch /usr/local/bin/*.sh

RUN chown -R elasticsearch:root /usr/share/elasticsearch/backups \
    && chmod -R 775 /usr/share/elasticsearch/backups
    
RUN echo "xpack.security.enabled: false" >> /usr/share/elasticsearch/config/elasticsearch.yml && \
    echo "xpack.security.transport.ssl.enabled: false" >> /usr/share/elasticsearch/config/elasticsearch.yml && \
    echo "xpack.security.http.ssl.enabled: false" >> /usr/share/elasticsearch/config/elasticsearch.yml && \
    echo "discovery.type: single-node" >> /usr/share/elasticsearch/config/elasticsearch.yml && \
    echo 'path.repo: ["/usr/share/elasticsearch/backups"]' >> /usr/share/elasticsearch/config/elasticsearch.yml

USER elasticsearch

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
