# Use a slim Python base image for efficiency
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy application code
COPY instance-manager.py .
#COPY .env .
COPY instance_groups.json .

# Install uv for dependency management
RUN pip install uv

# Install dependencies using uv
RUN uv pip install --system fastmcp oci

# Expose port for FastMCP server
EXPOSE 9000

# Run the FastMCP server
CMD ["uv", "run", "python", "instance-manager.py"]