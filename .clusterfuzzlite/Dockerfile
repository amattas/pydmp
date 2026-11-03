FROM gcr.io/oss-fuzz-base/base-builder-python

# Fleet-standard fuzz toolchain (same as ics-combiner): pydmp requires Python >=3.12; the base image
# ships 3.11. Put a pinned python-build-standalone 3.14 first on PATH so
# compile_python_fuzzer's pyinstaller and the fuzz target run on it.
ARG PYTHON_URL=https://github.com/astral-sh/python-build-standalone/releases/download/20261013/cpython-3.14.8%2B20261013-x86_64-unknown-linux-gnu-install_only.tar.gz
ARG PYTHON_SHA256=322271a761140ffb3f522431048f701831e412c8f64770103d2b881ee2bbaed0
RUN curl -fsSL -o /tmp/python.tar.gz "$PYTHON_URL" \
    && echo "$PYTHON_SHA256  /tmp/python.tar.gz" | sha256sum --check --strict \
    && tar -xzf /tmp/python.tar.gz -C /opt \
    && rm /tmp/python.tar.gz
ENV PATH=/opt/python/bin:$PATH
RUN python3 -m pip install --no-cache-dir atheris==3.1.0 pyinstaller==6.22.3

COPY . $SRC/pydmp
WORKDIR $SRC/pydmp
COPY .clusterfuzzlite/build.sh $SRC/
