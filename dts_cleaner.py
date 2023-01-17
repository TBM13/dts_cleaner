import os
import re
import sys

PHANDLE_VARS_OUTPUT="phandles.txt"
PHANDLE_PATTERN = re.compile(r'^( |\t)*phandle = <(.+?)>;$', re.MULTILINE)

def main():
    if len(sys.argv) != 2:
        print("Usage: dts_cleaner.py <dts>")
        print("This script will automatically detect if the dts" +
              "was grabbed from the kernel source code or from a compiled DTB.\n" +
              "In the first case, it'll write to 'phandles.txt' which variables" +
              "are phandles, while in the second case it'll replace in a copy" +
              "of the dts the value of these variables with their actual pointer name.")
        sys.exit(1)

    dts_path = sys.argv[1]
    if not os.path.isfile(dts_path):
        print(f"File not found: '{dts_path}'")
        sys.exit(2)

    with open(dts_path, 'r') as dts:
        content = dts.read()

        if re.search(PHANDLE_PATTERN, content) is None:
            print("DTS from kernel source detected, exporting phandle variables...")
            export_phandle_vars(content)
        else:
            out_file = f"{dts_path}_cleaned"
            print(f"DTS from compiled DTB detected, replacing phandles " +
                  f"and saving to '{out_file}'...")
            replace_phandles(content, out_file)
    
    print("Done!")

def export_phandle_vars(content: str):
    var_pattern_1 = re.compile(r'^( |\t)*(.+?)( |\t)=( |\t)<(.+?>, <.+?)>;')
    var_pattern_2 = re.compile(r'^( |\t)*(.+?)( |\t)=( |\t)<(.+?)>;')
    phandle_vars = set()

    lines_to_skip = 0
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if lines_to_skip > 0:
            lines_to_skip -= 1
            continue

        if not "&" in line or not "=" in line:
            continue

        while not line.endswith(';'):
            lines_to_skip += 1
            line = line.strip() + ' ' + lines[i + lines_to_skip].strip()
            
        if not "&" in line:
            continue

        m = re.match(var_pattern_1, line)
        if m is None:
            m = re.match(var_pattern_2, line)
            if m is None:
                # print(repr(line) + " ##")
                continue

        name = m.group(2)
        i = 0
        for v in m.group(5).split('>, <'):
            for v2 in v.split(' '):
                if v2.startswith('&'):
                    phandle_vars.add(f'{name}<{i}>')
                i += 1

    if not os.path.isfile(PHANDLE_VARS_OUTPUT):
        open(PHANDLE_VARS_OUTPUT, 'w').close()

    with open(PHANDLE_VARS_OUTPUT, 'r+') as out:
        stored_vars = out.readlines()

        added_amount = len(phandle_vars)
        for var in stored_vars:
            var_name = var.removesuffix('\n')
            if not var_name in phandle_vars:
                phandle_vars.add(var_name)
            else:
                added_amount -= 1
        
        # We also want 'phandle = <X>;' replaced
        if not "phandle<0>" in phandle_vars:
            phandle_vars.add("phandle<0>")
            added_amount += 1

        out.seek(0)
        out.writelines(f'{v}\n' for v in phandle_vars)
        print(f"Added {added_amount} phandle variable names to " +
              f"{PHANDLE_VARS_OUTPUT}, adding a total of {len(phandle_vars)}")

def read_symbols(content: str) -> dict[str, str]:
    symbols_pattern = re.compile(r'( |\t)*__symbols__ {\n(.+?)};', re.DOTALL)
    m = re.search(symbols_pattern, content)
    if m is None:
        print("Error: Couldn't find symbols")
        sys.exit(4)
    
    symbols = m.group(2).splitlines()
    symbols_dict = {}
    for sym in symbols:
        sym = sym.strip()
        if len(sym) == 0:
            continue

        m = re.match(r'^(.+?) = "(.+?)";$', sym)
        if m is None:
            print(f"Warning: Couldn't parse symbol '{repr(sym)}'")
            continue
        
        symbols_dict[m.group(2)] = m.group(1)

    print(f"Registered {len(symbols_dict)} symbols")
    return symbols_dict

def read_phandle_paths(content: str) -> dict[str, str]:
    current_path = ""
    paths = {}

    for line in content.splitlines():
        line = line.strip()
        if line.endswith('{'):
            # print(f"open {line}")
            current_path += f"{line.strip(' {')}"
            if not current_path.endswith('/'):
                current_path += "/"
            # print(current_path)
            continue
        elif line.endswith('};'):
            # print(line)
            current_path = current_path.removesuffix('/')
            if len(current_path) > 0:
                current_path = current_path[:current_path.rindex('/') + 1]
            if len(current_path) == 0:
                current_path = "/"
            continue

        m = re.match(PHANDLE_PATTERN, line)
        if m is None:
            continue
            
        paths[m.group(2)] = current_path
    
    print(f"Registered the path of {len(paths)} phandles")
    return paths

def replace_phandles(content: str, out_file: str):
    if not os.path.isfile(PHANDLE_VARS_OUTPUT):
        print(f"Couldn't find '{PHANDLE_VARS_OUTPUT}'")
        print("Tip: You need to first run this script passing it " +
              "one or more DTS files from the kernel source code")
        sys.exit(3)
    
    symbols = read_symbols(content)
    paths = read_phandle_paths(content)
    if len(symbols) != len(paths):
        print(f"Warning: Amount of symbols doesn't match amount of " +
               "phandle paths, something may have gone wrong")

    lines = content.splitlines()
    with open(PHANDLE_VARS_OUTPUT, 'r') as phandle_vars:
        phandle_vars = phandle_vars.readlines()
        var_patterns = []
        for var in phandle_vars:
            var = var.rstrip()
            value_index = int(var[-2])
            var = var[:-3]

            value = '.+?'
            for i in range(value_index):
                value += ' .+?'

            value = value.removesuffix('.+?') + "(.+?)"

            p = re.compile(r'^( |\t)*' + var + r' = <' + value + r'(>| )')
            var_patterns.append(p)

        print("Replacing phandles... please wait")
        replaced=0
        for i, line in enumerate(lines):
            for pattern in var_patterns:
                m = re.match(pattern, line)
                if m is None:
                    continue

                phandle = m.group(2)
                if not phandle in paths.keys():
                    print(f"Warning: Couldn't find path of phandle '{phandle}'")
                    continue

                sym = symbols[paths[phandle].removesuffix('/')]
                lines[i] = lines[i].replace(m.group(2), f'&{sym}')
                replaced += 1
        
        print(f'{replaced} phandle references replaced with their symbol')
        with open(out_file, 'w') as out:
            out.writelines(f'{l}\n' for l in lines)

if __name__ == "__main__":
    main()