"""Integration test for CE API client - requires internet connection."""

import click

try:
    from .client import CompilerExplorerClient
    from .models import CompileRequest
except ImportError:
    # Support running as standalone script
    from client import CompilerExplorerClient
    from models import CompileRequest


@click.command()
@click.option("--compiler", default="x86-64 gcc 15.1", help="Compiler name to test with")
@click.option("--language", default="c++", help="Programming language")
def test_real_api(compiler, language):
    """Test against real Compiler Explorer API."""
    with CompilerExplorerClient() as client:
        # Test getting compilers
        click.echo(f"Getting {language} compilers...")
        compilers = client.get_compilers(language)
        click.echo(f"Found {len(compilers)} {language} compilers")

        # Find specified compiler - must be exact match
        gcc = client.find_compiler_by_name(compiler, language=language)
        if not gcc:
            click.echo(f"Compiler '{compiler}' not found!", err=True)
            raise click.Abort()

        click.echo(f"\nFound compiler: {gcc.name} (ID: {gcc.id})")

        # Test compilation
        click.echo("\nCompiling simple C++ code...")
        request = CompileRequest(
            source="""int add(int a, int b) {
    return a + b;
}

int main() {
    return add(5, 3);
}
""",
            compiler=gcc.id,
            options=["-O2"],
        )

        try:
            response = client.compile(request)
            click.echo(f"Compilation successful! Status code: {response.code}")
            click.echo(f"Number of assembly lines: {len(response.asm)}")

            # Print first few assembly lines
            click.echo("\nFirst 10 assembly lines:")
            for i, line in enumerate(response.asm[:10]):
                click.echo(f"  {i:3d}: {line.text}")
                if line.source:
                    click.echo(f"       -> source line {line.source.line}")

            # Show label definitions
            click.echo(f"\nFound {len(response.label_definitions)} label definitions:")
            for label, line_num in list(response.label_definitions.items())[:5]:
                click.echo(f"  {label}: line {line_num}")
            if len(response.label_definitions) > 5:
                click.echo(f"  ... and {len(response.label_definitions) - 5} more")

        except Exception as e:
            click.echo(f"Compilation failed: {e}", err=True)
            raise click.Abort() from e


if __name__ == "__main__":
    test_real_api()
