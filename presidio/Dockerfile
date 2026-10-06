# Presidio analyzer with Chinese NER, for the egress content gate's
# contextual detector (nexus-vfs `egress_gate`, feature `presidio`).
#
# The official image is multi-arch, so this builds natively on the DGX
# (arm64) as well as on an amd64 workstation.
FROM mcr.microsoft.com/presidio-analyzer:latest

USER root
# ~575 MB. The large pipeline because NER quality is the whole reason this
# service exists; the deterministic rules already cover the cheap cases.
RUN python -m spacy download zh_core_web_lg

COPY conf/ /app/conf-zh/
ENV NLP_CONF_FILE=/app/conf-zh/nlp.yaml \
    ANALYZER_CONF_FILE=/app/conf-zh/analyzer.yaml \
    RECOGNIZER_REGISTRY_CONF_FILE=/app/conf-zh/recognizers.yaml
USER 1001
