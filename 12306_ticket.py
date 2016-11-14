"""12306 tickets query system by CLI

Usage:
    tickets.py [-gdtkz] [-as] <from> <to> [<date>]
    tickets.py -v | --version
    tickets.py -h | --help
    tickets.py --dump

Arguments:
  <from>            出发站
  <to>              到达站
  <date>            出发日期

Options:
    -h, --help      帮助
    -v, --version   版本

    --dump          显示站名表

    -a, --adult     成人票
    -s, --student   学生票

    -g              高铁
    -d              动车
    -t              特快
    -k              快速
    -z              直达


Examples:
    tickets.py shanghai beijing 2016-09-19
"""

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

import logging
import re
import datetime
import docopt
import prettytable

query_url = 'https://kyfw.12306.cn/otn/leftTicket/queryT?' \
            'leftTicketDTO.train_date={}&' \
            'leftTicketDTO.from_station={}&' \
            'leftTicketDTO.to_station={}&' \
            'purpose_codes={}'

station_js_url = 'https://kyfw.12306.cn/otn/resources/js/framework/station_name.js?station_version=1.8966'

table_header = '显示车次|出发/到达站|出发/到达时间|历时|一等坐|二等坐|软卧|软座|硬卧|硬座|无座'.split('|')


class TrainItem:
    def __init__(self, raw_dict, colored=False):
        self.raw_dict = raw_dict
        self.colored = colored

    def __str__(self):
        return '<TrainItem: {}>'.format(self.raw_dict['station_train_code'])

    @staticmethod
    def to_time(s):
        return s.replace(':', 'h') + 'm'

    def colorized(self, color, text):
        table = {
            'red': '\033[91m',
            'green': '\033[92m',
            'nc': '\033[0m',
        }
        cv = table.get(color)
        nc = table.get('nc')

        if self.colored:
            return ''.join([cv, text, nc])
        else:
            return text

    def output(self):
        li = [
            # 车次
            self.raw_dict['station_train_code'],
            # 出发站 -> 到达站
            '\n'.join((self.colorized('green', self.raw_dict['from_station_name']),
                       self.colorized('red', self.raw_dict['to_station_name']))),
            # 出发时间 -> 到达时间
            '\n'.join((self.colorized('green', self.raw_dict['start_time']),
                       self.colorized('red', self.raw_dict['arrive_time']))),
            # 历时
            self.to_time(self.raw_dict['lishi']),
            # 一等坐
            self.raw_dict['zy_num'],
            # 二等坐
            self.raw_dict['ze_num'],
            # 软卧
            self.raw_dict['rw_num'],
            # 软坐
            self.raw_dict['yw_num'],
            # 硬坐
            self.raw_dict['yz_num'],
            # 硬卧
            self.raw_dict['yw_num'],
            # 无座
            self.raw_dict['wz_num'],
        ]

        return li


def get_station_name_mapping():
    r = requests.get(station_js_url, headers={'User-Agent': 'chrome'}, verify=False)
    try:
        r.raise_for_status()
        data = re.findall(r'([A-Z]{3})\|([a-z]+)', r.text)
        data_table = re.findall(r'(\w+)\|([A-Z]{3})\|([a-z]+)', r.text)
        data = dict(data)
        data = dict(zip(data.values(), data.keys()))
    except requests.HTTPError:
        logging.exception('Query name convert js failed')
    except Exception:
        logging.exception('Unexpected error')
    else:
        return data, data_table


def table_output(headers, data):
    pt = prettytable.PrettyTable(headers)
    pt.padding_width = 1
    pt.hrules = prettytable.FRAME

    for item in data:
        pt.add_row(item)

    print(pt)


def cli():
    arguments = docopt.docopt(__doc__, version='1.0')
    from_station = arguments['<from>']
    to_station = arguments['<to>']
    date = arguments.get('<date>') or datetime.date.today()
    flag = []
    dump = arguments['--dump']

    if arguments['-g']:
        flag.append('G')
    if arguments['-d']:
        flag.append('D')
    if arguments['-t']:
        flag.append('T')
    if arguments['-k']:
        flag.append('K')
    if arguments['-z']:
        flag.append('Z')

    if not flag:
        flag = list('GDTKZ')

    pessenger = ''
    if arguments['--adult']:
        pessenger = 'ADULT'
    elif arguments['--student']:
        pessenger = '0X00'

    # get station mapping
    stations, dump_table = get_station_name_mapping()

    if dump and dump_table:
        table_output('显示名称|代号|名称'.split('|'), dump_table)
        return

    if stations:
        # make query
        try:
            complete_query_url = query_url.format(date,
                                                  stations[from_station],
                                                  stations[to_station],
                                                  pessenger)
            r = requests.get(complete_query_url,
                             headers={'User-Agent': 'chrome'},
                             verify=False)
            r.raise_for_status()
            json_data = r.json()

            x = [TrainItem(item['queryLeftNewDTO']).output()
                 for item in json_data['data']
                 if item['queryLeftNewDTO']['station_train_code'][0] in flag]

            table_output(table_header, x)

        except requests.HTTPError:
            logging.exception('Make query failed.')
        except KeyError:
            logging.exception('Query location not found.')


if __name__ == '__main__':
    cli()
