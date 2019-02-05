FROM openjdk:8-jdk-alpine

EXPOSE 8182
ENV VERSION 4.0.3
ENV HOSTNAME http://localhost

RUN adduser -S cantaloupe

RUN apk add --update curl openjpeg-tools
RUN curl -0L https://github.com/medusa-project/cantaloupe/releases/download/v$VERSION/cantaloupe-$VERSION.zip > /cantaloupe-$VERSION.zip
RUN unzip /cantaloupe-$VERSION.zip
COPY cantaloupe.properties /etc/cantaloupe.properties

RUN chown -R cantaloupe /cantaloupe-${VERSION} && chown cantaloupe /etc/cantaloupe.properties

USER cantaloupe
CMD ["sh", "-c", "java -Dcantaloupe.config=/etc/cantaloupe.properties -Xmx2g -jar /cantaloupe-$VERSION/cantaloupe-$VERSION.war"]

# docker build -t cantaloupe .
# docker run -p 8182:8182 -v /Users/rstorey/cantaloupe/images:/images --name cantaloupe cantaloupe