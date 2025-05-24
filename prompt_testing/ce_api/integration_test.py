"""Integration test for CE API client - requires internet connection."""

import sys

from .client import CompilerExplorerClient
from .models import CompileRequest


def test_real_api():
    """Test against real Compiler Explorer API."""
    with CompilerExplorerClient() as client:
        # Test getting compilers
        print("Getting C++ compilers...")
        compilers = client.get_compilers("c++")
        print(f"Found {len(compilers)} C++ compilers")

        # Find GCC compiler - must be exact match
        gcc = client.find_compiler_by_name("x86-64 gcc 15.1", language="c++")
        if not gcc:
            print("Compiler 'x86-64 gcc 15.1' not found!")
            sys.exit(1)

        print(f"\nFound compiler: {gcc.name} (ID: {gcc.id})")

        # Test compilation
        print("\nCompiling simple C++ code...")
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
            print(f"Compilation successful! Status code: {response.code}")
            print(f"Number of assembly lines: {len(response.asm)}")

            # Print first few assembly lines
            print("\nFirst 10 assembly lines:")
            for i, line in enumerate(response.asm[:10]):
                print(f"  {i:3d}: {line.text}")
                if line.source:
                    print(f"       -> source line {line.source.line}")

            # Show label definitions
            print(f"\nFound {len(response.label_definitions)} label definitions:")
            for label, line_num in list(response.label_definitions.items())[:5]:
                print(f"  {label}: line {line_num}")
            if len(response.label_definitions) > 5:
                print(f"  ... and {len(response.label_definitions) - 5} more")

        except Exception as e:
            print(f"Compilation failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    test_real_api()
