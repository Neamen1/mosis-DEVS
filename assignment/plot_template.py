def make_plot_products_script(config: str, strategy: str, max_waits: list[float], gen_num: int):
    return (f"""
### config={config}, strategy={strategy} ###

set terminal svg size 1200 900

# plot 1. x-axis: products, y-axis: flow time of product

set out 'plot_products_{config}_{strategy}.svg'
set title "Flow Time (config={config}, strategy={strategy})"
set xlabel "Product #"
set ylabel "Minutes"
set key title "Max Wait (min)"
set key bottom center out
set key horizontal

# set yrange [0:90]
set xrange [0:{gen_num}]
set style fill solid

plot 'output_{config}_{strategy}.csv' \\
    """ + ", \\\n '' ".join([
        f"using 1:{i+2} title '{max_wait:.0f}' w boxes ls {i+1}"
        for i, max_wait in enumerate(max_waits)
    ]))


def make_plot_box_script(config: str, strategy: str, max_waits: list[float], gen_num: int):
    return (f"""

# plot 2. x-axis: max-wait parameter, y-axis: flow times of products

set out 'plot_box_{config}_{strategy}.svg'
set title "Flow Time Distribution (config={config}, strategy={strategy})"
set style fill solid 0.25 border -1
set style boxplot outliers pointtype 7
set style data boxplot
set key off

set xlabel "Max Wait (minutes)"
unset xrange
unset yrange

set xtics (""" + ', '.join([f"'{max_wait:.0f}' {i}"
    for i, max_wait in enumerate(max_waits)]) + f""")

plot 'output_{config}_{strategy}.csv' \\
    """ + ", \\\n  '' ".join([
        f"using ({i}):{i+2} title '{max_wait:.0f}'"
        for i, max_wait in enumerate(max_waits)
    ]))


def make_plot_frequency_script(config: str, strategy: str, max_waits: list[float], gen_num: int):
    return (f"""

# plot 3. x-axis: flow time interval, y-axis: number of products

bin_width = 5;  # 5 minutes

set out 'plot_freq_{config}_{strategy}.svg'
set title "Frequency of flow times (config={config}, strategy={strategy})"
set boxwidth (bin_width) absolute
set style fill solid 1.0 noborder

set key title "Max Wait (min)"
set key bottom center out
# set key horizontal

set xtics auto
set xrange [0:]
set xlabel "Flow Time (minutes, interval)"
set ylabel "Number of products"

bin_number(x) = floor(x/bin_width)
rounded(x) = bin_width * ( bin_number(x) + 0.5 )

plot 'output_{config}_{strategy}.csv' \\
    """ + ", \\\n '' ".join([
        f"using (rounded(${i+2})):(1) title '{max_wait:.0f}' smooth frequency with boxes"
        for i, max_wait in list(enumerate(max_waits))
    ]))

