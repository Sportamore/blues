$TTL	{{ ttl }}
@	IN	SOA	{{ zone }}. root.{{ zone }}. (
			{{ serial }}		; Serial
			{{ ttl }}		; Refresh
			86400		; Retry
			2419200		; Expire
			{{ ttl }} )	; Negative Cache TTL
