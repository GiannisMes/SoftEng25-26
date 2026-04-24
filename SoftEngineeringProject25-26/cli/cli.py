#!/usr/bin/env python3
import argparse
import requests
import sys
import json 

BASE_URL = "http://127.0.0.1:9876/api"

def print_response(response):
    print(f"--- Debug: Status Code {response.status_code} ---") 
    try:
        data = response.json()
        print(json.dumps(data, indent=4, ensure_ascii=False))
    except:
        print("Body:", response.text)
        
def main():
    parser = argparse.ArgumentParser(description="SoftEng2025 Team 17 CLI Tool")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    #   --- ADMIN COMMANDS ---
    subparsers.add_parser('healthcheck')
    subparsers.add_parser('resetpoints', help="Reset all points to default values")

    add_p = subparsers.add_parser('addpoints', help='Add from CSV')
    add_p.add_argument('--source', type=str, required=True, help="Path to csv")

    # --- POINT COMMANDS ---
    get_points = subparsers.add_parser('points')
    get_points.add_argument('--status', type=str)
    get_points.add_argument('--format', choices=['json', 'csv'], default='json')
    
    get_point = subparsers.add_parser('point') 
    get_point.add_argument('--id', type=int, required=True)

    upd_p = subparsers.add_parser('updpoint')
    upd_p.add_argument('--id', type=int, required=True)
    upd_p.add_argument('--status', type=str)
    upd_p.add_argument('--price', type=float)

    p_stat = subparsers.add_parser('pointstatus') 
    p_stat.add_argument('--id', type=int, required=True)
    p_stat.add_argument('--from', dest='from_date', required=True)
    p_stat.add_argument('--to', dest='to_date', required=True)
    p_stat.add_argument('--format', choices=['json', 'csv'], default='json')

    # --- SESSION/USER COMMANDS ---
    res_p = subparsers.add_parser('reserve')
    res_p.add_argument('--id', type=int, required=True)
    res_p.add_argument('--minutes', type=int, default=30)

    new_ses = subparsers.add_parser('newsession')
    new_ses.add_argument('--id', type=int, required=True)
    new_ses.add_argument('--starttime', required=True)
    new_ses.add_argument('--endtime', required=True)
    new_ses.add_argument('--startsoc', type=int, required=True)
    new_ses.add_argument('--endsoc', type=int, required=True)
    new_ses.add_argument('--totalkwh', type=float, required=True)
    new_ses.add_argument('--kwhprice', type=float, required=True)
    new_ses.add_argument('--amount', type=float, required=True)

    get_ses = subparsers.add_parser('sessions')
    get_ses.add_argument('--id', type=int, required=True)
    get_ses.add_argument('--from', dest='from_date', required=True)
    get_ses.add_argument('--to', dest='to_date', required=True)
    get_ses.add_argument('--format', choices=['json', 'csv'], default='json')

    args = parser.parse_args()

    # EXECUTION LOGIC 
    try:
        if args.command == 'healthcheck':
            r = requests.get(f"{BASE_URL}/admin/healthcheck")
            print_response(r)
        
        elif args.command == 'resetpoints':
            r = requests.post(f"{BASE_URL}/admin/resetpoints")
            print_response(r)

        elif args.command == 'addpoints':
            with open(args.source, 'rb') as f:
                files = {'file': (args.source, f, 'text/csv')}
                r = requests.post(f"{BASE_URL}/admin/addpoints", files=files)
            print_response(r)

        elif args.command == 'points':
            params = {"status": args.status, "format": args.format}
            r = requests.get(f"{BASE_URL}/points", params=params)
            print_response(r)

        elif args.command == 'point':
            r = requests.get(f"{BASE_URL}/point/{args.id}")
            print_response(r)

        elif args.command == 'updpoint':
            if not args.id:
                print("Error: --id is required for updating a point")
                return
            if not args.status and not args.price:
                print("Error: Required parameter either --status or --price")
                return
            
            payload = {}
            if args.status: payload['status'] = args.status
            # Βεβαιώσου ότι το API περιμένει 'kwhprice' ή 'price'
            if args.price: payload['kwh_price'] = float(args.price) 
            
            # Χρήση PUT ή POST ανάλογα με το τι έχεις ορίσει στο Flask
            r = requests.post(f"{BASE_URL}/updpoint/{args.id}", json=payload)
            print_response(r)

        elif args.command == 'pointstatus':
            # Change the times into the correct format
            safe_from = args.from_date.replace(" ", "%20")
            safe_to = args.to_date.replace(" ", "%20")

            url = f"{BASE_URL}/pointstatus/{args.id}/{safe_from}/{safe_to}"
            r = requests.get(url)
            print_response(r)
                    
        elif args.command == 'reserve':
            if not args.id: 
                print("Error: --id required")
                return
            
            url = f"{BASE_URL}/reserve/{args.id}/{args.minutes}" if args.minutes else f"{BASE_URL}/reserve/{args.id}"
            
            payload = {"username": "admin"} 
            
            r = requests.post(url, json=payload) 
            print_response(r)

        elif args.command == 'newsession':
            payload = {
                "id": args.id,
                "starttime": args.starttime,
                "endtime": args.endtime,
                "startsoc": args.startsoc,
                "endsoc": args.endsoc,
                "totalkwh": args.totalkwh,
                "kwhprice": args.kwhprice,
                "amount": args.amount
            }
            r = requests.post(f"{BASE_URL}/newsession", json=payload)
            print_response(r)

        elif args.command == 'sessions':
            # Change the times into the correct format
            safe_from = args.from_date.replace(" ", "%20")
            safe_to = args.to_date.replace(" ", "%20")

            url = f"{BASE_URL}/sessions/{args.id}/{safe_from}/{safe_to}"
            r = requests.get(url)
            print_response(r)

    except requests.exceptions.ConnectionError:
        print("Error: Server won't respond.")
        
if __name__ == "__main__":
    main()